import os

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.6-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
TOP_K_TOOLS = int(os.getenv("TOP_K_TOOLS", "3"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() in {"1", "true", "yes"}
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "0" if OFFLINE_MODE else "25"))