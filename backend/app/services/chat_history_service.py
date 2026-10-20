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
                    is_error INTEGER DEFAULT 0,
                    suggested_questions TEXT -- JSON list of follow-up questions
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_doc_id ON messages (doc_id)
            """)
            # Migration support if table already existed without suggested_questions column
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN suggested_questions TEXT")
            except Exception:
                pass
            # Migration support for source_details column
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN source_details TEXT")
            except Exception:
                pass
            conn.commit()

    def add_message(
        self,
        doc_id: str,
        role: str,
        content: str,
        sources: Optional[List[int]] = None,
        is_error: bool = False,
        timestamp: Optional[str] = None,
        suggested_questions: Optional[List[str]] = None,
        source_details: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Adds a message to the persistent database."""
        if not timestamp:
            timestamp = datetime.now().strftime("%I:%M %p")
        sources_json = json.dumps(sources or [])
        seq_questions_json = json.dumps(suggested_questions or []) if suggested_questions else "[]"
        source_details_json = json.dumps(source_details or []) if source_details else "[]"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (doc_id, role, content, sources, timestamp, is_error, suggested_questions, source_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, role, content, sources_json, timestamp, 1 if is_error else 0, seq_questions_json, source_details_json))
            msg_id = cursor.lastrowid
            conn.commit()

            return {
                "id": msg_id,
                "doc_id": doc_id,
                "role": role,
                "content": content,
                "sources": sources or [],
                "source_details": source_details or [],
                "suggested_questions": suggested_questions or [],
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
                SELECT id, doc_id, role, content, sources, timestamp, is_error, suggested_questions, source_details
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

                seq_questions = []
                try:
                    if "suggested_questions" in r.keys() and r["suggested_questions"]:
                        seq_questions = json.loads(r["suggested_questions"])
                except Exception:
                    seq_questions = []

                details_list = []
                try:
                    if "source_details" in r.keys() and r["source_details"]:
                        details_list = json.loads(r["source_details"])
                except Exception:
                    details_list = []

                result.append({
                    "id": r["id"],
                    "doc_id": r["doc_id"],
                    "role": r["role"],
                    "content": r["content"],
                    "sources": sources_list,
                    "source_details": details_list,
                    "suggested_questions": seq_questions,
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
