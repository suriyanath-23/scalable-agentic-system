import json
import re
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph

from config import EMBEDDING_MODEL, MAX_RETRIES, MODEL_NAME, OFFLINE_MODE, TOP_K_TOOLS
from core.observability import tracer
from core.registry import UniversalToolRegistry
from core.state import UniversalAgentState
from tools import MANDATORY_TOOL_MAP, create_dynamic_tool
from tools.executor import mock_network_executor

# 1. Initialize Registry
registry = UniversalToolRegistry(embedding_model=EMBEDDING_MODEL, offline=OFFLINE_MODE)
registry.load_postman_collection("data/postman_collection.json")
registry.load_postman_collection("data/paypal_additional_collection.json")
registry.build_index()

# 2. Base Gemini Chat Model (max_retries=0 allows main.py to handle backoff cleanly)
base_llm = None if OFFLINE_MODE else ChatGoogleGenerativeAI(model=MODEL_NAME, max_retries=0)


def dynamic_retrieval_node(state: UniversalAgentState) -> dict[str, Any]:
    last_human_msg = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )
    query_text = last_human_msg
    if state.get("error_flag"):
        last_tool_msg = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, ToolMessage)),
            "",
        )
        query_text = f"{last_human_msg} {last_tool_msg}"

    k = TOP_K_TOOLS + 2 if state.get("error_flag") else TOP_K_TOOLS
    matched_specs = registry.retrieve_top_k(query_text, k=k)
    active_names = [s["name"] for s in matched_specs]

    # Preserve mandatory tools permanently
    for mandatory in MANDATORY_TOOL_MAP:
        if mandatory not in active_names:
            active_names.append(mandatory)

    tracer.emit("tool_retrieval", query=query_text, selected_tools=active_names, top_k=k)
    return {"active_tools": active_names}


def agent_reasoning_node(state: UniversalAgentState) -> dict[str, Any]:
    if OFFLINE_MODE:
        last_message = state["messages"][-1]
        if isinstance(last_message, ToolMessage):
            results = []
            for message in reversed(state["messages"]):
                if not isinstance(message, ToolMessage):
                    break
                results.append(f"{message.name}: {message.content}")
            response = AIMessage(content="\n".join(reversed(results)))
            tracer.emit("agent_response", mode="offline", tool_calls=[])
            return {"messages": [response]}

        query = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            "",
        )
        lowered = query.lower()
        tool_name = None
        args: dict[str, str] = {}
        if "invoice" in lowered and ("send" in lowered or "create" in lowered):
            tool_name = "paypal_create_invoice"
            email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", query)
            amount = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", query)
            if email:
                args["recipient"] = email.group(0)
            if amount:
                args["amount"] = amount.group(1)
        elif "sales volume" in lowered:
            tool_name = "paypal_get_sales_volume"
            args["period"] = "last_month" if "last month" in lowered else "today"
        elif "dispute" in lowered and "tool" not in lowered and "capabilit" not in lowered:
            tool_name = "paypal_check_dispute"
            user = re.search(r"user[_-]?[A-Za-z0-9]+", query, re.IGNORECASE)
            if user:
                args["user_id"] = user.group(0)
        elif "tool" in lowered or "capabilit" in lowered or "status" in lowered:
            tool_name = "system_search_tool"
            args["query"] = query
        elif any(word in lowered for word in ("policy", "guide", "documentation")):
            tool_name = "rag_pipeline_tool"
            args["query"] = query

        if tool_name:
            tracer.emit("agent_response", mode="offline", tool_calls=[tool_name])
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": tool_name, "args": args, "id": str(uuid4()), "type": "tool_call"}
                        ],
                    )
                ]
            }
        tracer.emit("agent_response", mode="offline", tool_calls=[])
        return {"messages": [AIMessage(content="I could not map that request to a registered tool.")]}

    runnable_tools = []
    for name in state["active_tools"]:
        if name in MANDATORY_TOOL_MAP:
            runnable_tools.append(MANDATORY_TOOL_MAP[name])
        elif name in registry.tool_definitions:
            runnable_tools.append(create_dynamic_tool(registry.tool_definitions[name]))

    llm_with_tools = base_llm.bind_tools(runnable_tools)
    response = llm_with_tools.invoke(state["messages"])
    tracer.emit("agent_response", mode="live", tool_calls=[call["name"] for call in response.tool_calls])
    return {"messages": [response]}


def execution_node(state: UniversalAgentState) -> dict[str, Any]:
    last_msg = state["messages"][-1]
    tool_messages = []
    has_error = False
    system_logs = list(state.get("system_logs", []))
    error_log = list(state.get("error_log", []))

    for call in last_msg.tool_calls:
        name = call["name"]
        args = call["args"]
        call_id = call["id"]

        try:
            if name == "rag_pipeline_tool":
                res = MANDATORY_TOOL_MAP["rag_pipeline_tool"].invoke(args)
            elif name == "system_search_tool":
                res = MANDATORY_TOOL_MAP["system_search_tool"].invoke(args)
            elif name in registry.tool_definitions:
                spec = registry.tool_definitions[name]
                res = mock_network_executor(name, spec["method"], spec["url"], **args)
            else:
                raise KeyError(f"Tool '{name}' is not recognized in active registry.")
        except Exception as e:  # noqa: BLE001
            has_error = True
            error_log.append({"tool": name, "error_type": type(e).__name__, "details": str(e)})
            res = json.dumps({
                "status": "ERROR",
                "error_type": type(e).__name__,
                "details": str(e),
                "instruction": "The previous tool call failed. Reflect on parameters or call system_search_tool.",
            })

        # Name and tool_call_id are both required by the model schema
        tool_messages.append(
            ToolMessage(content=str(res), name=name, tool_call_id=call_id)
        )
        system_logs.append(f"Executed {name}: {'error' if has_error else 'success'}")
        tracer.emit("tool_execution", tool=name, status="error" if has_error else "success")

    current_retries = state.get("retry_count", 0)
    return {
        "messages": tool_messages,
        "error_flag": has_error,
        "retry_count": current_retries + 1 if has_error else 0,
        "system_logs": system_logs,
        "error_log": error_log,
    }


def route_condition(state: UniversalAgentState):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        if state.get("retry_count", 0) >= MAX_RETRIES:
            return "circuit_break"
        return "execute"
    return END


def fallback_recovery_node(state: UniversalAgentState) -> dict[str, Any]:
    fallback_message = AIMessage(
        content="I encountered consecutive errors while attempting to fulfill this request. "
        "Operation was halted to prevent an infinite loop. "
        "Please verify your inputs or use system search to check available tools."
    )
    return {"messages": [fallback_message], "error_flag": False, "retry_count": 0}


# LangGraph Compilation
builder = StateGraph(UniversalAgentState)
builder.add_node("retrieve", dynamic_retrieval_node)
builder.add_node("agent", agent_reasoning_node)
builder.add_node("execute", execution_node)
builder.add_node("circuit_break", fallback_recovery_node)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "agent")
builder.add_conditional_edges(
    "agent",
    route_condition,
    {
        "execute": "execute",
        "circuit_break": "circuit_break",
        END: END,
    },
)
builder.add_edge("execute", "agent")
builder.add_edge("circuit_break", END)

agent_system = builder.compile()