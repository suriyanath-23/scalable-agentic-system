import json
import sys
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from config import COOLDOWN_SECONDS, MODEL_NAME, OFFLINE_MODE
from graph.workflow import agent_system, registry


def safe_invoke(state: dict[str, Any], max_attempts: int = 4) -> dict[str, Any]:
    """Catches SDK & API errors and formats them into clean, readable terminal alerts."""
    for attempt in range(max_attempts):
        try:
            return agent_system.invoke(state)
        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)

            # 1. Daily Quota Limit (RPD)
            if (
                "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in err_msg
                or "limit: 20" in err_msg
                or "quotaValue': '20'" in err_msg
            ):
                print("\n" + "=" * 80)
                print("  [ERROR: DAILY API QUOTA DEPLETED]")
                print("=" * 80)
                print("  Cause   : The Google Free Tier enforces a strict 20 request/day ceiling.")
                print("  Status  : This limit resets at midnight Pacific Time (PT).")
                print("  Fix     : 1. Go to https://aistudio.google.com/")
                print("            2. Click 'Get API key' -> 'Create API key in NEW project'.")
                print("            3. Paste the new key into your .env file.")
                print("=" * 80 + "\n")
                sys.exit(1)

            # 2. Model Not Found or Deprecated (404)
            elif "404" in err_msg or "NOT_FOUND" in err_msg:
                print("\n" + "=" * 80)
                print("  [ERROR: MODEL TARGET UNAVAILABLE]")
                print("=" * 80)
                print(f"  Cause   : Model '{MODEL_NAME}' is deprecated or not recognized.")
                print("  Fix     : Update MODEL_NAME=gemini-3.6-flash in your .env file.")
                print("=" * 80 + "\n")
                sys.exit(1)

            # 3. Per-Minute Rate Limit (429 RPM)
            elif "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                wait_time = 25 * (attempt + 1)
                print(
                    f"\n  [Notice] Per-minute rate limit hit. Pausing {wait_time}s "
                    f"(Attempt {attempt + 1}/{max_attempts}) before retrying..."
                )
                time.sleep(wait_time)

            # 4. Google Server High Traffic (503)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                wait_time = 20 * (attempt + 1)
                print(
                    f"\n  [Notice] Google servers temporarily at peak capacity (503). "
                    f"Waiting {wait_time}s to retry..."
                )
                time.sleep(wait_time)

            else:
                print("\n" + "=" * 80)
                print("  [SYSTEM RUNTIME ERROR]")
                print("=" * 80)
                print(f"  Details : {err_msg.strip().splitlines()[-1]}")
                print("=" * 80 + "\n")
                sys.exit(1)

    print("\n[Failure]: Agent failed to complete the task after maximum retry attempts.")
    sys.exit(1)


def print_section_divider(title: str):
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def print_key_value(label: str, value: Any):
    print(f"  {label:<22}: {value}")


def format_result(raw_output: str) -> str:
    try:
        return json.dumps(json.loads(raw_output), indent=2)
    except (TypeError, json.JSONDecodeError):
        return str(raw_output)


def format_plain_answer(raw_answer: Any) -> str:
    text = str(raw_answer)
    if not text or text == "[]":
        return "The system completed the request without a written response."

    if ": {" in text:
        _, payload = text.split(": ", 1)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return text

        if data.get("status") == "SENT" and data.get("invoice_id"):
            return (
                f"Invoice sent successfully to {data.get('recipient')}. "
                f"Amount: {data.get('amount')} {data.get('currency', 'USD')}. "
                f"Invoice ID: {data['invoice_id']}."
            )
        if "total_sales_volume" in data:
            return (
                f"Total sales volume: {data['total_sales_volume']:,.2f} {data.get('currency', '')}. "
                f"Settled transactions: {data.get('settled_transactions', 'not available')}."
            )
        if "dispute_open" in data:
            status = "An open dispute was found." if data["dispute_open"] else "No open dispute was found."
            return f"{status} Dispute ID: {data.get('dispute_id', 'not available')}."
        if data.get("matching_tools"):
            return (
                "The system is operational. Matching tools found: "
                + ", ".join(data["matching_tools"])
                + "."
            )

    return text


def run_project_verification():
    queries = [
        "Send an invoice for $50 to client@company.com",
        "What was my total sales volume last month?",
        "Is there a dispute open from user_123?",
        "What tools are available for managing invoices and checking disputes?",
    ]

    print_section_divider("SCALABLE AGENTIC SYSTEM: INTERNAL PIPELINE BENCHMARK")
    print(f"Active Model Target : {MODEL_NAME}")
    print(f"Execution Mode      : {'OFFLINE' if OFFLINE_MODE else 'LIVE'}")
    print(f"Registered Endpoints: {len(registry.tool_definitions)}")
    print(f"Total Test Cases    : {len(queries)}")

    for idx, query in enumerate(queries, 1):
        print(f"\n>>> QUERY [{idx}/{len(queries)}]")
        print(f'User Input Intent: "{query}"')
        print("-" * 80)

        initial_state = {
            "messages": [HumanMessage(content=query)],
            "retry_count": 0,
            "error_log": [],
            "error_flag": False,
            "active_tools": [],
            "system_logs": [],
        }

        result = safe_invoke(initial_state)
        messages = result.get("messages", [])
        active_tools = result.get("active_tools", [])

        print("\n[PHASE 1: UNDERSTANDING THE REQUEST]")
        print("  The system searched its catalog and selected only the most relevant tools.")
        print_key_value("Available tools", len(registry.tool_definitions))
        print_key_value("Tools considered", len(active_tools))
        print_key_value("Selected tools", ", ".join(active_tools))
        print_key_value("Safety tools always available", "Knowledge search, system search")

        print("\n[PHASE 2: TAKING ACTION]")
        print("  The system chose an action and received the following result:")
        executed_calls = []
        final_answer = ""

        for msg in messages:
            if isinstance(msg, AIMessage):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for call in msg.tool_calls:
                        executed_calls.append(
                            {
                                "name": call.get("name"),
                                "args": call.get("args"),
                            }
                        )
                if msg.content:
                    final_answer = msg.content
            elif isinstance(msg, ToolMessage):
                for call in executed_calls:
                    if call["name"] == msg.name:
                        call["output"] = msg.content

        if executed_calls:
            for step_num, call in enumerate(executed_calls, 1):
                print(f"\n  Action {step_num}: {call['name']}")
                print_key_value("Information used", json.dumps(call["args"]))
                print("  Result:")
                for line in format_result(call.get("output", "No result returned")).splitlines():
                    print(f"    {line}")
        else:
            print("  No external action was needed; the system answered directly.")

        print("\n[PHASE 3: ANSWER]")
        print("  This is the system's plain-language response:")
        if isinstance(final_answer, list):
            clean_text = "\n".join(
                part.get("text", "")
                for part in final_answer
                if isinstance(part, dict)
            )
        else:
            clean_text = str(final_answer)

        for line in format_plain_answer(clean_text).strip().split("\n"):
            print(f"  {line}")

        print("-" * 80)

        # Pacing cooldown to respect free-tier per-minute ceilings
        if idx < len(queries) and COOLDOWN_SECONDS:
            print(f"Cooldown pacing ({COOLDOWN_SECONDS}s delay between benchmark iterations)...")
            time.sleep(COOLDOWN_SECONDS)


if __name__ == "__main__":
    run_project_verification()