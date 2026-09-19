import sys


class DiagnosticReporter:
    @staticmethod
    def print_banner(
        category: str,
        title: str,
        reason: str,
        fix_action: str,
        details: str = "",
    ):
        print("\n" + "=" * 80)
        print(f"  [{category.upper()}: {title.upper()}]")
        print("=" * 80)
        print(f"  Reason      : {reason}")
        print(f"  Resolution  : {fix_action}")
        if details:
            print(f"  Diagnostics : {details}")
        print("=" * 80 + "\n")

    @classmethod
    def handle_exception(cls, exc: Exception, context: str = "Runtime"):
        raw_msg = str(exc)

        # 1. Daily Quota Limit (RPD)
        if (
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in raw_msg
            or "limit: 20" in raw_msg
            or "quotaValue': '20'" in raw_msg
        ):
            cls.print_banner(
                category="API Quota Depleted",
                title="Daily Free-Tier Ceiling Reached (429)",
                reason="The Google AI Studio Free Tier allows up to 20 requests/day per project for preview models.",
                fix_action="Create a new project key at https://aistudio.google.com/ and update GEMINI_API_KEY in .env.",
                details="Counter resets at midnight Pacific Time (PT).",
            )
            sys.exit(0)

        # 2. Model 404 / Deprecation (Embedding or Chat)
        elif "404" in raw_msg or "NOT_FOUND" in raw_msg:
            if "embedContent" in raw_msg or "embedding" in raw_msg:
                cls.print_banner(
                    category="Configuration Error",
                    title="Embedding Model Endpoint Deprecated or Not Found (404)",
                    reason="The specified embedding model is deprecated or not available on API version v1beta.",
                    fix_action="Update .env to EMBEDDING_MODEL=models/gemini-embedding-001 (or run without 'models/' prefix).",
                    details=raw_msg.splitlines()[-1],
                )
            else:
                cls.print_banner(
                    category="Configuration Error",
                    title="LLM Chat Model Unavailable (404)",
                    reason="The selected model name was not found or is restricted.",
                    fix_action="Set MODEL_NAME=gemini-3.6-flash in .env.",
                    details=raw_msg.splitlines()[-1],
                )
            sys.exit(0)

        # 3. Authentication & Key Errors
        elif (
            "API_KEY_INVALID" in raw_msg
            or "401" in raw_msg
            or "PERMISSION_DENIED" in raw_msg
            or "403" in raw_msg
        ):
            cls.print_banner(
                category="Authentication Failure",
                title="Invalid or Restricted Google API Key",
                reason="The provided key was rejected by Google GenAI services.",
                fix_action="Verify GEMINI_API_KEY in .env has active permissions and has not been revoked.",
                details=raw_msg.splitlines()[-1],
            )
            sys.exit(0)

        # 4. Fallback for unclassified errors
        else:
            cls.print_banner(
                category="System Error",
                title=f"Exception Encountered in [{context}]",
                reason=type(exc).__name__,
                fix_action="Inspect state logs or tool registration parameters.",
                details=raw_msg.strip().splitlines()[-1],
            )
            sys.exit(0)