import json
import os
import threading
import time
from pathlib import Path
from typing import Any


class JsonTracer:
    """Small external-tracer-compatible JSONL sink for local and CI runs."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("TRACE_FILE", "data/traces.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, event: str, **fields: Any):
        payload = {
            "timestamp": time.time(),
            "event": event,
            **fields,
        }
        with self._lock, self.path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(payload, default=str) + "\n")


tracer = JsonTracer()
