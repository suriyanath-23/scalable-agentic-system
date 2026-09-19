from pathlib import Path

from core.retrieval import PersistentHybridIndex


class KnowledgeBase:
    """Chunked document store backed by the same persistent hybrid index."""

    def __init__(self, documents_path: str = "data/knowledge_base", index_path: str = "data/retrieval.db"):
        self.documents_path = Path(documents_path)
        self.index = PersistentHybridIndex(index_path)
        self.ingest()

    def ingest(self):
        for document_path in sorted(self.documents_path.glob("*.md")):
            chunks = [chunk.strip() for chunk in document_path.read_text(encoding="utf-8").split("\n\n") if chunk.strip()]
            for chunk_number, chunk in enumerate(chunks, 1):
                name = f"{document_path.stem}:{chunk_number}"
                self.index.upsert(
                    "knowledge",
                    name,
                    chunk,
                    {"source": document_path.name, "chunk": chunk_number},
                )

    def search(self, query: str, k: int = 3) -> list[dict]:
        return self.index.search("knowledge", query, k=k)
