import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any


class PersistentHybridIndex:
    """SQLite-backed lexical plus deterministic vector retrieval index."""

    dimensions = 128

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                collection TEXT NOT NULL,
                name TEXT NOT NULL,
                text TEXT NOT NULL,
                metadata TEXT NOT NULL,
                vector TEXT NOT NULL,
                PRIMARY KEY (collection, name)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                collection UNINDEXED,
                name UNINDEXED,
                text,
                metadata UNINDEXED
            );
            """
        )
        self.connection.commit()

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9_]+", text.lower())

    @classmethod
    def _vectorize(cls, text: str) -> list[float]:
        vector = [0.0] * cls.dimensions
        for token in cls._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % cls.dimensions
            vector[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector

    def upsert(self, collection: str, name: str, text: str, metadata: dict[str, Any]):
        encoded_metadata = json.dumps(metadata, sort_keys=True)
        vector = json.dumps(self._vectorize(text))
        self.connection.execute(
            "DELETE FROM records_fts WHERE collection = ? AND name = ?",
            (collection, name),
        )
        self.connection.execute(
            """
            INSERT INTO records(collection, name, text, metadata, vector)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(collection, name) DO UPDATE SET
                text = excluded.text,
                metadata = excluded.metadata,
                vector = excluded.vector
            """,
            (collection, name, text, encoded_metadata, vector),
        )
        self.connection.execute(
            "INSERT INTO records_fts(collection, name, text, metadata) VALUES (?, ?, ?, ?)",
            (collection, name, text, encoded_metadata),
        )
        self.connection.commit()

    def search(self, collection: str, query: str, k: int = 3) -> list[dict[str, Any]]:
        query_tokens = self._tokens(query)
        fts_query = " OR ".join(query_tokens)
        if fts_query:
            rows = self.connection.execute(
                """
                SELECT r.name, r.text, r.metadata, r.vector
                FROM records r
                JOIN records_fts f ON f.collection = r.collection AND f.name = r.name
                WHERE r.collection = ? AND records_fts MATCH ?
                """,
                (collection, fts_query),
            ).fetchall()
        else:
            rows = []

        if len(rows) < k:
            existing = {row[0] for row in rows}
            fallback = self.connection.execute(
                "SELECT name, text, metadata, vector FROM records WHERE collection = ?",
                (collection,),
            ).fetchall()
            rows.extend(row for row in fallback if row[0] not in existing)

        query_vector = self._vectorize(query)
        scored = []
        query_set = set(query_tokens)
        for name, text, metadata, vector_json in rows:
            text_tokens = set(self._tokens(text))
            lexical = len(query_set & text_tokens) / max(len(query_set), 1)
            vector = json.loads(vector_json)
            cosine = sum(left * right for left, right in zip(query_vector, vector))
            scored.append((0.65 * lexical + 0.35 * cosine, name, text, metadata))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "name": name,
                "text": text,
                "metadata": json.loads(metadata),
                "score": round(score, 4),
            }
            for score, name, text, metadata in scored[:k]
        ]

    def close(self):
        self.connection.close()
