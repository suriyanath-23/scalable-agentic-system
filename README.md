# Scalable Agentic System

This project demonstrates a LangGraph agent that selects a small, relevant tool subset from a larger PayPal catalog. The included catalog contains 55 endpoints across invoicing, disputes, reporting, checkout, payments, subscriptions, payouts, and webhooks.

## Run

The default mode is deterministic and offline, so the benchmark does not consume Gemini quota:

```powershell
python main.py
```

Set `OFFLINE_MODE=false` and provide a newly rotated `GEMINI_API_KEY` in `.env` to use Gemini for reasoning. The tool registry remains local and persistent in both modes.

Run tests with:

```powershell
python -m unittest discover -s tests -v
```

## Architecture

1. `UniversalToolRegistry` loads one or more Postman collections and persists tool metadata in SQLite.
2. `PersistentHybridIndex` combines SQLite FTS5 lexical matching with deterministic hashed-token cosine vectors. This keeps retrieval local, reproducible, and persistent without requiring an embedding API at startup.
3. The graph retrieves only the top-k endpoint schemas and always adds the RAG and system-search tools.
4. `KnowledgeBase` chunks Markdown documents and indexes them in the `knowledge` collection. The RAG tool returns source names and scores with each result.
5. `JsonTracer` writes structured JSONL events for retrieval, model decisions, and tool execution to `data/traces.jsonl`.

## Trade-offs

- SQLite is simple, portable, and adequate for a single process or moderate catalog. A production deployment with millions of records should move the index to a managed search/vector service.
- Hashed-token vectors are deterministic and dependency-free, but less semantically rich than a hosted embedding model. A production adapter can replace `_vectorize` while preserving the index contract.
- Offline routing makes the benchmark reliable and testable, but it is intentionally limited. Live Gemini mode provides general natural-language planning.
- The endpoint executor is still a deterministic simulator. Real PayPal adapters must add OAuth, timeouts, retries, response schemas, idempotency keys, authorization, and confirmation for high-risk operations.

## Data and generated files

- `data/postman_collection.json` contains the original endpoints.
- `data/paypal_additional_collection.json` expands the catalog to 57 total endpoints.
- `data/knowledge_base/` contains source documents for the RAG pipeline.
- `data/retrieval.db` and `data/traces.jsonl` are local generated artifacts and are ignored by Git.
