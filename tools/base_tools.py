import json
from typing import Any

from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field, create_model

from core.knowledge_base import KnowledgeBase
from core.retrieval import PersistentHybridIndex
from tools.executor import mock_network_executor

knowledge_base = KnowledgeBase()
tool_index = PersistentHybridIndex("data/retrieval.db")


def _index_catalog_files():
    for collection_path in ("data/postman_collection.json", "data/paypal_additional_collection.json"):
        with open(collection_path, "r", encoding="utf-8") as collection_file:
            data = json.load(collection_file)
        for spec in data.get("item", []):
            text = (
                f"Endpoint: {spec['name']} | Purpose: {spec.get('description', '')} | "
                f"Parameters: {list(spec.get('parameters', {}))}"
            )
            tool_index.upsert("tools", spec["name"], text, {"name": spec["name"]})


_index_catalog_files()


class RagQueryInput(BaseModel):
    query: str = Field(description="The query regarding external policies, guides, or documentation")


@tool("rag_pipeline_tool", args_schema=RagQueryInput)
def rag_pipeline_tool(query: str) -> str:
    """Query documentation and knowledge base for policies, operating limits, and guidelines."""
    results = knowledge_base.search(query)
    return json.dumps({
        "source": "Knowledge_Base_v2",
        "results": [
            {"source": result["metadata"]["source"], "text": result["text"], "score": result["score"]}
            for result in results
        ],
    })


class SystemSearchInput(BaseModel):
    query: str = Field(description="Query to inspect system status, tools, capabilities, or logs")


@tool("system_search_tool", args_schema=SystemSearchInput)
def system_search_tool(query: str) -> str:
    """Search the system capabilities, view available tools, or query execution logs."""
    results = tool_index.search("tools", query, k=10)
    return json.dumps({
        "status": "OPERATIONAL",
        "engine": "LangGraph Cyclical State Machine",
        "retrieval": "SQLite FTS5 plus deterministic vector hybrid index",
        "matching_tools": [result["name"] for result in results],
        "registered_modules": ["paypal_invoicing", "paypal_disputes", "paypal_reporting", "rag_pipeline"],
    })


def create_dynamic_tool(spec: dict[str, Any]) -> StructuredTool:
    """Dynamically creates a LangChain StructuredTool from an endpoint schema."""
    fields = {}
    for param_name, param_info in spec.get("parameters", {}).items():
        optional = param_name in {"note", "reason", "note_to_paypal"}
        param_type = str | None if optional else str
        desc = param_info if isinstance(param_info, str) else param_info.get("description", "")
        default = None if optional else ...
        fields[param_name] = (param_type, Field(default=default, description=desc))

    args_schema = create_model(f"{spec['name']}Schema", **fields)

    def dynamic_func(**kwargs):
        return mock_network_executor(
            tool_name=spec["name"],
            method=spec["method"],
            url=spec["url"],
            **kwargs,
        )

    return StructuredTool(
        name=spec["name"],
        description=spec["description"],
        func=dynamic_func,
        args_schema=args_schema,
    )


MANDATORY_TOOL_MAP = {
    "rag_pipeline_tool": rag_pipeline_tool,
    "system_search_tool": system_search_tool,
}