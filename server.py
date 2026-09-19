from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from graph.workflow import agent_system, registry


app = FastAPI(
    title="Scalable Agentic System",
    description="Natural-language routing across a large PayPal tool catalog.",
    version="1.0.0",
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    active_tools: list[str]
    error_log: list[dict[str, Any]]


def _message_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(
        part.get("text", "")
        for part in message.content
        if isinstance(part, dict) and part.get("text")
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "registered_endpoints": len(registry.tool_definitions),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    state = {
        "messages": [HumanMessage(content=request.message)],
        "active_tools": [],
        "system_logs": [],
        "retry_count": 0,
        "error_flag": False,
        "error_log": [],
    }

    try:
        result = agent_system.invoke(state)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Agent execution failed") from exc

    messages = result.get("messages", [])
    answer = _message_text(messages[-1]) if messages else "No answer was produced."
    return ChatResponse(
        answer=answer,
        active_tools=result.get("active_tools", []),
        error_log=result.get("error_log", []),
    )
