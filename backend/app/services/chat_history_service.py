import sqlite3
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

class ChatHistoryService:
    """
    SQLite persistent storage for chat messages associated with each document.
    Stores messages per doc_id so conversation history is preserved across page
    refreshes and file switching.
    """
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            # Check vector_db directory in project root or backend
            if (base_dir / "vector_db").exists():
                self.db_path = base_dir / "vector_db" / "chat_history.db"
            elif (base_dir.parent / "vector_db").exists():
                self.db_path = base_dir.parent / "vector_db" / "chat_history.db"
            else:
                self.db_path = base_dir / "vector_db" / "chat_history.db"
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources TEXT, -- JSON list of page numbers
                    timestamp TEXT NOT NULL,
                    is_error INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_doc_id ON messages (doc_id)
            """)
            conn.commit()

    def add_message(
        self,
        doc_id: str,
        role: str,
        content: str,
        sources: Optional[List[int]] = None,
        is_error: bool = False,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """Adds a message to the persistent database."""
        if not timestamp:
            timestamp = datetime.now().strftime("%I:%M %p")
        sources_json = json.dumps(sources or [])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (doc_id, role, content, sources, timestamp, is_error)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (doc_id, role, content, sources_json, timestamp, 1 if is_error else 0))
            msg_id = cursor.lastrowid
            conn.commit()

            return {
                "id": msg_id,
                "doc_id": doc_id,
                "role": role,
                "content": content,
                "sources": sources or [],
                "timestamp": timestamp,
                "time": timestamp,
                "is_error": is_error,
                "isError": is_error
            }

    def get_messages(self, doc_id: str) -> List[Dict[str, Any]]:
        """Retrieves all chat messages for a document in chronological order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, doc_id, role, content, sources, timestamp, is_error
                FROM messages
                WHERE doc_id = ?
                ORDER BY id ASC
            """, (doc_id,))
            rows = cursor.fetchall()

            result = []
            for r in rows:
                sources_list = []
                if r["sources"]:
                    try:
                        sources_list = json.loads(r["sources"])
                    except Exception:
                        sources_list = []

                result.append({
                    "id": r["id"],
                    "doc_id": r["doc_id"],
                    "role": r["role"],
                    "content": r["content"],
                    "sources": sources_list,
                    "timestamp": r["timestamp"],
                    "time": r["timestamp"],
                    "isError": bool(r["is_error"])
                })
            return result

    def clear_messages(self, doc_id: str) -> bool:
        """Deletes all messages for a specific document."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return True
