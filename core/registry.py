import json
import typing
from pathlib import Path

from core.retrieval import PersistentHybridIndex


class UniversalToolRegistry:
    """Persistent hybrid registry with lexical and vector retrieval."""

    def __init__(self, embedding_model: str, offline: bool = False, index_path: str | None = None):
        self.offline = offline
        self.tool_definitions: dict[str, dict[str, typing.Any]] = {}
        self.index = PersistentHybridIndex(index_path or "data/retrieval.db")

    def load_postman_collection(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data.get("item", [])
        self._load_items(items)

    def _load_items(self, items: list[dict[str, typing.Any]]):
        for item in items:
            if item.get("item"):
                self._load_items(item["item"])
                continue
            name = item["name"]
            desc = item.get("description", "")
            method = item.get("request", {}).get("method", "GET")
            raw_url = item.get("request", {}).get("url", "")
            url = raw_url.get("raw", "") if isinstance(raw_url, dict) else raw_url
            params = item.get("parameters", {})

            self.tool_definitions[name] = {
                "name": name,
                "description": desc,
                "method": method.upper(),
                "url": url,
                "parameters": params,
            }

    def build_index(self):
        for spec in self.tool_definitions.values():
            text = (
                f"Endpoint: {spec['name']} | Purpose: {spec['description']} | "
                f"Parameters: {list(spec['parameters'].keys())}"
            )
            self.index.upsert("tools", spec["name"], text, spec)

    def retrieve_top_k(self, query: str, k: int = 3) -> list[dict[str, typing.Any]]:
        results = self.index.search("tools", query, k=k)
        retrieved_names = [result["name"] for result in results]
        return [
            self.tool_definitions[name]
            for name in retrieved_names
            if name in self.tool_definitions
        ]

    def close(self):
        self.index.close()