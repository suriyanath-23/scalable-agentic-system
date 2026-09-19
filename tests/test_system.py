import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from core.knowledge_base import KnowledgeBase
from core.registry import UniversalToolRegistry
from core.retrieval import PersistentHybridIndex
from server import app
from tools.base_tools import create_dynamic_tool, rag_pipeline_tool, system_search_tool
from tools.executor import mock_network_executor


class RetrievalTests(unittest.TestCase):
    def test_hybrid_index_persists_and_ranks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.db"
            index = PersistentHybridIndex(path)
            index.upsert("tools", "invoice", "create and send customer invoice", {})
            index.upsert("tools", "dispute", "inspect seller dispute evidence", {})
            index.close()
            reopened = PersistentHybridIndex(path)
            results = reopened.search("tools", "send an invoice", k=1)
            self.assertEqual(results[0]["name"], "invoice")
            reopened.close()

    def test_registry_loads_extended_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = UniversalToolRegistry(
                "models/test",
                offline=True,
                index_path=Path(directory) / "tools.db",
            )
            registry.load_postman_collection("data/postman_collection.json")
            registry.load_postman_collection("data/paypal_additional_collection.json")
            registry.build_index()
            self.assertGreaterEqual(len(registry.tool_definitions), 50)
            self.assertEqual(
                registry.retrieve_top_k("sales volume report", 1)[0]["name"],
                "paypal_get_sales_volume",
            )
            registry.close()


class ToolTests(unittest.TestCase):
    def test_invoice_schema_and_output(self):
        spec = {
            "name": "paypal_create_invoice",
            "description": "Create invoice",
            "method": "POST",
            "url": "https://example.test/invoices",
            "parameters": {
                "recipient": {"description": "Customer email"},
                "amount": {"description": "Amount"},
                "note": {"description": "Optional note"},
            },
        }
        tool = create_dynamic_tool(spec)
        result = json.loads(tool.invoke({"recipient": "a@example.com", "amount": "50"}))
        self.assertEqual(result["recipient"], "a@example.com")

    def test_rag_returns_sources(self):
        result = json.loads(rag_pipeline_tool.invoke({"query": "invoice fees"}))
        self.assertTrue(result["results"])
        self.assertIn("source", result["results"][0])

    def test_system_search_returns_matches(self):
        result = json.loads(system_search_tool.invoke({"query": "sales volume"}))
        self.assertIn("paypal_get_sales_volume", result["matching_tools"])


class ApiTests(unittest.TestCase):
    def test_health_and_chat_endpoints(self):
        client = TestClient(app)
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["registered_endpoints"], 57)

        response = client.post(
            "/chat",
            json={"message": "What was my total sales volume last month?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("paypal_get_sales_volume", response.json()["answer"])


if __name__ == "__main__":
    unittest.main()
