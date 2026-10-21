"""
Lightweight ChromaDB Drop-In Replacement (light_chroma.py)
---------------------------------------------------------
A pure-Python, zero-heavy-dependency vector database client that replaces ChromaDB
for environments like Vercel Serverless Functions where ONNXRuntime, PyTorch,
Transformers, Tokenizers, and HuggingFace (>450MB) blow past the 500MB function limit.

Compatible with ChromaDB's core interface:
  - chromadb.PersistentClient(path=...)
  - client.get_or_create_collection(name=..., metadata=...)
  - collection.add(ids=..., documents=..., metadatas=...)
  - collection.query(query_texts=..., n_results=..., where=...)
  - collection.get(ids=..., where=..., include=...)
  - collection.count()
  - collection.delete(ids=..., where=...)
"""

import os
import re
import math
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union


def _tokenize(text: str) -> List[str]:
    """Extracts lowercase alpha-numeric words for scoring."""
    if not text:
        return []
    return [w.lower() for w in re.findall(r"\w+", text) if len(w) > 1]


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class LightCollection:
    def __init__(self, name: str, db_dir: Path, metadata: Optional[Dict[str, Any]] = None):
        self.name = str(name)
        self.id = f"col_{self.name}"
        if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            self.db_dir = Path("/tmp/vector_db")
        else:
            try:
                self.db_dir = Path(db_dir)
                self.db_dir.mkdir(parents=True, exist_ok=True)
                test_f = self.db_dir / ".write_test"
                test_f.touch()
                test_f.unlink()
            except (OSError, PermissionError):
                self.db_dir = Path("/tmp/vector_db")
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = self.db_dir / "chroma.sqlite3"
        self.metadata = metadata or {}
        self._init_db()

    def modify(self, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        if name:
            self.name = str(name)
        if metadata:
            self.metadata.update(metadata)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS light_chunks (
                    id TEXT PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    document TEXT NOT NULL,
                    metadata_json TEXT,
                    embedding_json TEXT,
                    doc_id TEXT,
                    user_id TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_col ON light_chunks (collection_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_doc ON light_chunks (doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_user ON light_chunks (user_id)")
            conn.commit()

    def count(self) -> int:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM light_chunks WHERE collection_name = ?", (self.name,))
            row = cur.fetchone()
            cnt = row[0] if row else 0
            if cnt > 0:
                return cnt

            # Fallback only for global default collection if light_chunks has not been populated yet
            if self.name == "task_rag_vector_store":
                try:
                    cur.execute("SELECT COUNT(*) FROM embeddings")
                    legacy_row = cur.fetchone()
                    if legacy_row and legacy_row[0] > 0:
                        return legacy_row[0]
                except Exception:
                    pass
            return 0

    def add(
        self,
        ids: List[str],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[Any]] = None
    ):
        if not ids or not documents:
            return

        metas = metadatas or [{} for _ in ids]
        embs = embeddings or [None for _ in ids]

        with self._get_connection() as conn:
            cur = conn.cursor()
            for chunk_id, doc, meta, emb in zip(ids, documents, metas, embs):
                meta_clean = meta or {}
                doc_id = str(meta_clean.get("doc_id", ""))
                user_id = str(meta_clean.get("user_id", ""))
                meta_json = json.dumps(meta_clean)
                emb_json = json.dumps(emb) if emb else None

                cur.execute("""
                    INSERT OR REPLACE INTO light_chunks
                    (id, collection_name, document, metadata_json, embedding_json, doc_id, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (chunk_id, self.name, doc, meta_json, emb_json, doc_id, user_id))
            conn.commit()

    def get(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            query = "SELECT id, document, metadata_json, embedding_json FROM light_chunks WHERE collection_name = ?"
            params = [self.name]

            if ids:
                placeholders = ",".join("?" for _ in ids)
                query += f" AND id IN ({placeholders})"
                params.extend(ids)

            if where:
                for k, v in where.items():
                    if k == "doc_id":
                        query += " AND doc_id = ?"
                        params.append(str(v))
                    elif k == "user_id":
                        query += " AND user_id = ?"
                        params.append(str(v))

            cur.execute(query, params)
            rows = cur.fetchall()

            res_ids = []
            res_docs = []
            res_metas = []

            for r in rows:
                res_ids.append(r["id"])
                res_docs.append(r["document"])
                try:
                    res_metas.append(json.loads(r["metadata_json"]) if r["metadata_json"] else {})
                except Exception:
                    res_metas.append({})

            # If light_chunks is empty for this query, attempt to read from legacy ChromaDB schema
            if not res_ids and (not ids or len(ids) == 0):
                try:
                    cur.execute("SELECT id, document FROM embeddings LIMIT 100")
                    l_rows = cur.fetchall()
                    for lr in l_rows:
                        res_ids.append(lr[0])
                        res_docs.append(lr[1] or "")
                        res_metas.append({})
                except Exception:
                    pass

            return {
                "ids": res_ids,
                "documents": res_docs,
                "metadatas": res_metas
            }

    def query(
        self,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[Any]] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        question = query_texts[0] if (query_texts and len(query_texts) > 0) else ""
        q_tokens = _tokenize(question)

        with self._get_connection() as conn:
            cur = conn.cursor()
            query = "SELECT id, document, metadata_json, embedding_json FROM light_chunks WHERE collection_name = ?"
            params = [self.name]

            if where:
                for k, v in where.items():
                    if k == "doc_id":
                        query += " AND doc_id = ?"
                        params.append(str(v))
                    elif k == "user_id":
                        query += " AND user_id = ?"
                        params.append(str(v))

            cur.execute(query, params)
            rows = cur.fetchall()

            scored_items = []
            for r in rows:
                doc_text = r["document"] or ""
                doc_tokens = _tokenize(doc_text)
                doc_token_set = set(doc_tokens)

                # 1. Term overlap score (BM25-style frequency relevance)
                if q_tokens:
                    matches = sum(1 for t in q_tokens if t in doc_token_set)
                    overlap_ratio = matches / len(q_tokens)
                else:
                    overlap_ratio = 0.5

                # 2. Substring matching bonus (for acronyms, phrases, names)
                phrase_bonus = 0.0
                if question and question.lower() in doc_text.lower():
                    phrase_bonus = 0.35
                elif any(t in doc_text.lower() for t in q_tokens if len(t) > 3):
                    phrase_bonus = 0.15

                # Chroma distance is (1.0 - similarity)
                total_score = min(1.0, overlap_ratio * 0.7 + phrase_bonus)
                distance = max(0.01, 1.0 - total_score)

                meta = {}
                try:
                    meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                except Exception:
                    pass

                scored_items.append((distance, r["id"], doc_text, meta))

            # Sort ascending by distance (lowest distance = most relevant)
            scored_items.sort(key=lambda x: x[0])
            top_k = scored_items[:n_results]

            ret_ids = [item[1] for item in top_k]
            ret_docs = [item[2] for item in top_k]
            ret_metas = [item[3] for item in top_k]
            ret_dists = [item[0] for item in top_k]

            return {
                "ids": [ret_ids],
                "documents": [ret_docs],
                "metadatas": [ret_metas],
                "distances": [ret_dists]
            }

    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None
    ):
        with self._get_connection() as conn:
            cur = conn.cursor()
            query = "DELETE FROM light_chunks WHERE collection_name = ?"
            params = [self.name]

            if ids:
                placeholders = ",".join("?" for _ in ids)
                query += f" AND id IN ({placeholders})"
                params.extend(ids)

            if where:
                for k, v in where.items():
                    if k == "doc_id":
                        query += " AND (doc_id = ? OR metadata_json LIKE ?)"
                        params.extend([str(v), f'%"doc_id": "{v}"%'])
                    elif k == "user_id":
                        query += " AND (user_id = ? OR metadata_json LIKE ?)"
                        params.extend([str(v), f'%"user_id": "{v}"%'])
                    else:
                        query += " AND metadata_json LIKE ?"
                        params.append(f'%"{k}": "{v}"%')

            cur.execute(query, params)
            conn.commit()


class LightClient:
    def __init__(self, path: Union[str, Path] = "./vector_db"):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self._collections: Dict[str, LightCollection] = {}

    def get_or_create_collection(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LightCollection:
        if name not in self._collections:
            self._collections[name] = LightCollection(name, self.path, metadata)
        return self._collections[name]

    def get_collection(self, name: str) -> LightCollection:
        return self.get_or_create_collection(name)

    def list_collections(self) -> List[LightCollection]:
        cols = dict(self._collections)
        sqlite_file = self.path / "chroma.sqlite3"
        if sqlite_file.exists():
            try:
                conn = sqlite3.connect(str(sqlite_file))
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT collection_name FROM light_chunks")
                for (cname,) in cur.fetchall():
                    if cname and cname not in cols:
                        cols[cname] = LightCollection(cname, self.path)
                conn.close()
            except Exception:
                pass
        return list(cols.values())

    def delete_collection(self, name: str):
        if name in self._collections:
            self._collections[name].delete()
            del self._collections[name]


def PersistentClient(path: Union[str, Path] = "./vector_db") -> LightClient:
    """Drop-in replacement for chromadb.PersistentClient."""
    return LightClient(path)
