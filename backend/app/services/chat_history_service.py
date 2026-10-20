import sqlite3
import json
import os
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

class ChatHistoryService:
    """
    SQLite persistent storage for chat sessions, messages, and file statuses.
    Supports ChatGPT-style multiple sessions per file and global 'All files' sessions,
    with time-based grouping, full-text search, auto-titling, and soft deletion of files.
    """
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
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

            # 1. Files table: tracking active/deleted status of uploaded documents
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active', -- 'active' or 'deleted'
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                )
            """)

            # 2. Chat sessions table (ChatGPT-style)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    scope TEXT NOT NULL, -- 'all' or 'file'
                    file_id TEXT,
                    file_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions (updated_at DESC)
            """)

            # 3. Legacy threads table for backwards compatibility
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS threads (
                    doc_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_deleted INTEGER DEFAULT 0,
                    deleted_at TEXT
                )
            """)

            # 4. Messages table storing questions and answers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT,
                    doc_id TEXT NOT NULL,
                    filename TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources TEXT, -- JSON list of page numbers
                    timestamp TEXT NOT NULL,
                    is_error INTEGER DEFAULT 0,
                    suggested_questions TEXT, -- JSON list of follow-up questions
                    source_details TEXT -- JSON list of source objects [{file_id, file_name, page}]
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_doc_id ON messages (doc_id)
            """)

            # Migrations for existing messages table
            columns = [col["name"] for col in cursor.execute("PRAGMA table_info(messages)").fetchall()]
            if "chat_id" not in columns:
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN chat_id TEXT")
                except Exception:
                    pass
            if "filename" not in columns:
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN filename TEXT")
                except Exception:
                    pass
            if "suggested_questions" not in columns:
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN suggested_questions TEXT")
                except Exception:
                    pass
            if "source_details" not in columns:
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN source_details TEXT")
                except Exception:
                    pass

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)
            """)

            # Migration: Ensure existing messages have chat_id populated from doc_id
            cursor.execute("UPDATE messages SET chat_id = doc_id WHERE chat_id IS NULL OR chat_id = ''")

            # Migration: Populate chat_sessions from threads or messages if empty
            cursor.execute("SELECT COUNT(*) as cnt FROM chat_sessions")
            row = cursor.fetchone()
            if row and row["cnt"] == 0:
                now_iso = datetime.utcnow().isoformat()
                cursor.execute("SELECT doc_id, filename, created_at, is_deleted FROM threads")
                old_threads = cursor.fetchall()
                for ot in old_threads:
                    d_id = ot["doc_id"]
                    fn = ot["filename"] or ("All files" if d_id == "all" else "Document")
                    sc = "all" if d_id == "all" else "file"
                    fid = None if d_id == "all" else d_id
                    cursor.execute("""
                        INSERT OR IGNORE INTO chat_sessions (id, title, scope, file_id, file_name, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (d_id, fn, sc, fid, fn, ot["created_at"] or now_iso, ot["created_at"] or now_iso))

            # Remove any 0-message sessions that were accidentally populated from raw file IDs
            cursor.execute("""
                DELETE FROM chat_sessions
                WHERE id NOT IN (SELECT DISTINCT chat_id FROM messages WHERE chat_id IS NOT NULL)
                  AND id NOT IN (SELECT DISTINCT doc_id FROM messages WHERE doc_id IS NOT NULL)
                  AND id NOT LIKE 'chat_%'
                  AND id != 'all'
            """)

            # Ensure at least one default "all" session exists
            cursor.execute("SELECT id FROM chat_sessions WHERE scope = 'all' LIMIT 1")
            if not cursor.fetchone():
                now_iso = datetime.utcnow().isoformat()
                cursor.execute("""
                    INSERT OR IGNORE INTO chat_sessions (id, title, scope, file_id, file_name, created_at, updated_at)
                    VALUES ('all', 'All files', 'all', NULL, 'All files', ?, ?)
                """, (now_iso, now_iso))

            conn.commit()

    # ==========================================
    # FILE MANAGEMENT (STATUS TRACKING & SOFT DELETION)
    # ==========================================

    def register_file(self, file_id: str, name: str, status: str = "active") -> Dict[str, Any]:
        """Registers or updates a file status in the SQLite DB."""
        if not file_id:
            return {}
        clean_id = file_id.strip()
        clean_name = name or "Document"
        now_iso = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, status FROM files WHERE id = ?", (clean_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE files SET name = ?, status = ?, deleted_at = NULL WHERE id = ?
                """, (clean_name, status, clean_id))
            else:
                cursor.execute("""
                    INSERT INTO files (id, name, status, created_at, deleted_at)
                    VALUES (?, ?, ?, ?, NULL)
                """, (clean_id, clean_name, status, now_iso))
            conn.commit()
            return {"id": clean_id, "name": clean_name, "status": status}

    def mark_file_deleted(self, file_id: str) -> bool:
        """
        Marks a file as 'deleted'.
        Preserves all chat sessions and messages for this file and copies the file name
        so chats remain viewable and marked 'File deleted' (read-only).
        """
        if not file_id or file_id == "all":
            return False
        clean_id = file_id.strip()
        now_iso = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM files WHERE id = ?", (clean_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE files SET status = 'deleted', deleted_at = ? WHERE id = ?
                """, (now_iso, clean_id))
            else:
                # Find filename from chat_sessions or messages
                cursor.execute("SELECT file_name FROM chat_sessions WHERE file_id = ? LIMIT 1", (clean_id,))
                s_row = cursor.fetchone()
                fn = s_row["file_name"] if s_row and s_row["file_name"] else "Deleted Document"
                cursor.execute("""
                    INSERT INTO files (id, name, status, created_at, deleted_at)
                    VALUES (?, ?, 'deleted', ?, ?)
                """, (clean_id, fn, now_iso, now_iso))

            # Also maintain legacy threads table
            cursor.execute("""
                UPDATE threads SET is_deleted = 1, deleted_at = ? WHERE doc_id = ?
            """, (now_iso, clean_id))

            conn.commit()
            return True

    def is_file_deleted(self, file_id: Optional[str]) -> bool:
        """Checks if a file is marked as deleted."""
        if not file_id or file_id == "all":
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM files WHERE id = ?", (file_id.strip(),))
            row = cursor.fetchone()
            if row:
                return row["status"] == "deleted"
            # Fallback to threads table
            cursor.execute("SELECT is_deleted FROM threads WHERE doc_id = ?", (file_id.strip(),))
            t_row = cursor.fetchone()
            return bool(t_row and t_row["is_deleted"])

    def get_active_file_ids(self) -> Set[str]:
        """Returns set of all file IDs that are currently active."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM files WHERE status = 'active'")
            return {r["id"] for r in cursor.fetchall()}

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Returns file record."""
        if not file_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, status, created_at, deleted_at FROM files WHERE id = ?", (file_id,))
            r = cursor.fetchone()
            if r:
                return {
                    "id": r["id"],
                    "name": r["name"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "deleted_at": r["deleted_at"]
                }
            return None

    # ==========================================
    # CHAT SESSION MANAGEMENT (CHATGPT-STYLE)
    # ==========================================

    def create_session(
        self,
        scope: str = "all",
        file_id: Optional[str] = None,
        file_name: Optional[str] = None,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new independent chat session.
        A user can have multiple sessions for the same file or for 'All files'.
        """
        clean_scope = "file" if scope == "file" and file_id and file_id != "all" else "all"
        clean_file_id = file_id if clean_scope == "file" else None

        # Clean file name
        if clean_scope == "file":
            clean_fn = file_name
            if not clean_fn and clean_file_id:
                f_record = self.get_file(clean_file_id)
                clean_fn = f_record["name"] if f_record else "Document"
        else:
            clean_fn = "All files"

        # Default title
        if not title:
            clean_title = "New chat" if clean_scope == "all" else f"Chat: {clean_fn}"
        else:
            clean_title = title.strip()

        session_id = f"chat_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_sessions (id, title, scope, file_id, file_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, clean_title, clean_scope, clean_file_id, clean_fn, now_iso, now_iso))
            conn.commit()

        return {
            "id": session_id,
            "title": clean_title,
            "scope": clean_scope,
            "file_id": clean_file_id,
            "file_name": clean_fn,
            "is_file_deleted": self.is_file_deleted(clean_file_id),
            "created_at": now_iso,
            "updated_at": now_iso,
            "message_count": 0
        }

    def get_session(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves session details by id."""
        if not chat_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.title, s.scope, s.file_id, s.file_name, s.created_at, s.updated_at,
                       COUNT(m.id) as message_count
                FROM chat_sessions s
                LEFT JOIN messages m ON s.id = m.chat_id
                WHERE s.id = ?
                GROUP BY s.id
            """, (chat_id,))
            r = cursor.fetchone()
            if not r:
                # Backwards compatibility: check if chat_id matches a doc_id or 'all'
                cursor.execute("""
                    SELECT doc_id, filename, created_at, is_deleted FROM threads WHERE doc_id = ?
                """, (chat_id,))
                t = cursor.fetchone()
                if t:
                    scope = "all" if t["doc_id"] == "all" else "file"
                    return {
                        "id": t["doc_id"],
                        "title": t["filename"],
                        "scope": scope,
                        "file_id": None if scope == "all" else t["doc_id"],
                        "file_name": t["filename"],
                        "is_file_deleted": bool(t["is_deleted"]),
                        "created_at": t["created_at"],
                        "updated_at": t["created_at"],
                        "message_count": 0
                    }
                return None

            is_deleted = self.is_file_deleted(r["file_id"]) if r["scope"] == "file" else False
            return {
                "id": r["id"],
                "title": r["title"],
                "scope": r["scope"],
                "file_id": r["file_id"],
                "file_name": r["file_name"],
                "is_file_deleted": is_deleted,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "message_count": r["message_count"]
            }

    def get_sessions(self, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves all chat sessions in ONE unified list, ordered by updated_at DESC (newest first).
        When search_query is supplied, filters by title AND message content text.
        """
        clean_q = search_query.strip().lower() if search_query else ""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT s.id, s.title, s.scope, s.file_id, s.file_name, s.created_at, s.updated_at,
                       COUNT(m.id) as message_count,
                       MAX(m.id) as last_msg_id
                FROM chat_sessions s
                LEFT JOIN messages m ON s.id = m.chat_id
            """
            params = []

            if clean_q:
                query += """
                    WHERE LOWER(s.title) LIKE ?
                       OR s.id IN (
                           SELECT chat_id FROM messages WHERE LOWER(content) LIKE ?
                       )
                """
                like_term = f"%{clean_q}%"
                params.extend([like_term, like_term])

            query += """
                GROUP BY s.id
                HAVING COUNT(m.id) > 0 OR s.id LIKE 'chat_%'
                ORDER BY s.updated_at DESC
            """
            cursor.execute(query, params)
            rows = cursor.fetchall()

            result = []
            for r in rows:
                is_deleted = self.is_file_deleted(r["file_id"]) if r["scope"] == "file" else False
                result.append({
                    "id": r["id"],
                    "title": r["title"],
                    "scope": r["scope"],
                    "file_id": r["file_id"],
                    "file_name": r["file_name"] or ("All files" if r["scope"] == "all" else "Document"),
                    "is_file_deleted": is_deleted,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "message_count": r["message_count"]
                })
            return result

    def update_session_title(self, chat_id: str, title: str) -> bool:
        """Renames a chat session."""
        if not chat_id or not title:
            return False
        clean_title = title.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE chat_sessions SET title = ? WHERE id = ?
            """, (clean_title, chat_id))
            conn.commit()
            return cursor.rowcount > 0

    def touch_session(self, chat_id: str, updated_at: Optional[str] = None) -> bool:
        """Updates the updated_at timestamp of a chat session so it moves to top of list."""
        if not chat_id:
            return False
        now_iso = updated_at or datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE chat_sessions SET updated_at = ? WHERE id = ?
            """, (now_iso, chat_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_session(self, chat_id: str) -> bool:
        """
        Permanently deletes only that chat session and all its messages.
        Does not affect any other chat session or document.
        """
        if not chat_id:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE chat_id = ? OR (chat_id IS NULL AND doc_id = ?)", (chat_id, chat_id))
            cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (chat_id,))
            if chat_id != "all":
                cursor.execute("DELETE FROM threads WHERE doc_id = ?", (chat_id,))
            conn.commit()
            return True

    # ==========================================
    # MESSAGE MANAGEMENT
    # ==========================================

    def add_message(
        self,
        chat_id: Optional[str] = None,
        doc_id: Optional[str] = None,
        role: str = "user",
        content: str = "",
        filename: Optional[str] = None,
        sources: Optional[List[int]] = None,
        is_error: bool = False,
        timestamp: Optional[str] = None,
        suggested_questions: Optional[List[str]] = None,
        source_details: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Adds a message to persistent storage.
        Auto-generates title for the session on first user message if needed.
        Updates session's updated_at timestamp so it moves to top of sidebar.
        """
        clean_chat_id = (chat_id or doc_id or "all").strip()
        clean_doc_id = (doc_id or clean_chat_id or "all").strip()
        if not timestamp:
            timestamp = datetime.now().strftime("%I:%M %p")

        now_iso = datetime.utcnow().isoformat()

        # Ensure session exists
        session = self.get_session(clean_chat_id)
        if not session:
            # Auto-create session
            scope = "all" if clean_doc_id == "all" else "file"
            file_id = None if scope == "all" else clean_doc_id
            self.create_session(scope=scope, file_id=file_id, file_name=filename, title=filename or "New chat")
            session = self.get_session(clean_chat_id)

        # Auto-title from first user question if title is still default "New chat"
        if role == "user" and session:
            current_title = (session.get("title") or "").strip()
            if current_title in ("New chat", "All files", "Document") or current_title.startswith("Chat: "):
                # Trim question to about 40 characters for a clean title
                clean_q = content.strip().replace("\n", " ")
                if len(clean_q) > 42:
                    new_title = clean_q[:40].rstrip() + "..."
                else:
                    new_title = clean_q
                if new_title:
                    self.update_session_title(clean_chat_id, new_title)

        sources_json = json.dumps(sources or [])
        seq_questions_json = json.dumps(suggested_questions or []) if suggested_questions else "[]"
        source_details_json = json.dumps(source_details or []) if source_details else "[]"
        clean_fn = filename or (session.get("file_name") if session else None) or "Document"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (chat_id, doc_id, filename, role, content, sources, timestamp, is_error, suggested_questions, source_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (clean_chat_id, clean_doc_id, clean_fn, role, content, sources_json, timestamp, 1 if is_error else 0, seq_questions_json, source_details_json))
            msg_id = cursor.lastrowid

            # Update session's updated_at
            cursor.execute("""
                UPDATE chat_sessions SET updated_at = ? WHERE id = ?
            """, (now_iso, clean_chat_id))
            conn.commit()

            return {
                "id": msg_id,
                "chat_id": clean_chat_id,
                "doc_id": clean_doc_id,
                "filename": clean_fn,
                "role": role,
                "content": content,
                "text": content,
                "sources": sources or [],
                "source_details": source_details or [],
                "suggested_questions": suggested_questions or [],
                "timestamp": timestamp,
                "time": timestamp,
                "is_error": is_error,
                "isError": is_error
            }

    def get_messages(self, chat_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all chat messages for a chat session in chronological order.
        Also resolves if any source files are currently deleted so the UI can tag them.
        """
        if not chat_id:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, chat_id, doc_id, filename, role, content, sources, timestamp, is_error, suggested_questions, source_details
                FROM messages
                WHERE chat_id = ? OR (chat_id IS NULL AND doc_id = ?)
                ORDER BY id ASC
            """, (chat_id, chat_id))
            rows = cursor.fetchall()

            # Pre-fetch deleted file IDs to enrich source tags
            cursor.execute("SELECT id FROM files WHERE status = 'deleted'")
            deleted_file_ids = {r["id"] for r in cursor.fetchall()}
            cursor.execute("SELECT doc_id FROM threads WHERE is_deleted = 1")
            for r in cursor.fetchall():
                deleted_file_ids.add(r["doc_id"])

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
                        raw_details = json.loads(r["source_details"])
                        for d in raw_details:
                            fid = d.get("file_id") or d.get("doc_id")
                            is_del = fid in deleted_file_ids if fid else False
                            details_list.append({
                                "file_id": fid,
                                "doc_id": fid,
                                "filename": d.get("filename") or d.get("file_name", ""),
                                "file_name": d.get("filename") or d.get("file_name", ""),
                                "page": d.get("page", 1),
                                "is_deleted": is_del
                            })
                except Exception:
                    details_list = []

                result.append({
                    "id": r["id"],
                    "chat_id": r["chat_id"] or r["doc_id"],
                    "doc_id": r["doc_id"],
                    "filename": r["filename"] or "",
                    "role": r["role"],
                    "content": r["content"],
                    "text": r["content"],
                    "sources": sources_list,
                    "source_details": details_list,
                    "suggested_questions": seq_questions,
                    "timestamp": r["timestamp"],
                    "time": r["timestamp"],
                    "isError": bool(r["is_error"])
                })
            return result

    def get_safe_history_for_llm(self, chat_id: str, active_file_ids: Set[str]) -> List[Dict[str, str]]:
        """
        Retrieves prior conversation context for the LLM.
        CRITICAL NO-LEAKAGE RULE:
        Does NOT return any turn (user question or assistant answer) whose assistant
        answer utilized content from a file that is NOT in active_file_ids.
        Messages that used only active files can still be used as conversation context.
        """
        messages = self.get_messages(chat_id)
        if not messages:
            return []

        safe_turns: List[Dict[str, str]] = []
        pending_user_msg = None

        for m in messages:
            if m["role"] == "user":
                pending_user_msg = m["content"]
            elif m["role"] == "assistant":
                # Check sources
                details = m.get("source_details", [])
                has_deleted_source = False
                for d in details:
                    fid = d.get("file_id") or d.get("doc_id")
                    if fid and fid not in active_file_ids:
                        has_deleted_source = True
                        break

                if not has_deleted_source:
                    # Both user message and assistant message are safe to include
                    if pending_user_msg:
                        safe_turns.append({"role": "user", "content": pending_user_msg})
                    safe_turns.append({"role": "assistant", "content": m["content"]})

                pending_user_msg = None

        return safe_turns

    # ==========================================
    # LEGACY METHODS (BACKWARD COMPATIBILITY)
    # ==========================================

    def ensure_thread(self, doc_id: str, filename: str, is_deleted: int = 0) -> Dict[str, Any]:
        """Legacy helper maintained for compatibility."""
        clean_doc_id = (doc_id or "all").strip()
        clean_filename = filename or ("All files" if clean_doc_id == "all" else "Document")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT doc_id, filename, is_deleted FROM threads WHERE doc_id = ?", (clean_doc_id,))
            row = cursor.fetchone()
            if not row:
                now_iso = datetime.utcnow().isoformat()
                cursor.execute("""
                    INSERT INTO threads (doc_id, filename, created_at, is_deleted)
                    VALUES (?, ?, ?, ?)
                """, (clean_doc_id, clean_filename, now_iso, is_deleted))
            conn.commit()
        return {"doc_id": clean_doc_id, "filename": clean_filename, "is_deleted": is_deleted}

    def soft_delete_file(self, doc_id: str) -> bool:
        """Legacy helper: delegates to mark_file_deleted."""
        return self.mark_file_deleted(doc_id)

    def get_threads(self) -> List[Dict[str, Any]]:
        """Legacy helper: returns chat sessions mapped to thread structure."""
        sessions = self.get_sessions()
        threads = []
        for s in sessions:
            threads.append({
                "doc_id": s["id"],
                "chat_id": s["id"],
                "filename": s["file_name"],
                "title": s["title"],
                "scope": s["scope"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "is_deleted": s["is_file_deleted"],
                "message_count": s["message_count"]
            })
        return threads

    def delete_thread(self, doc_id: str) -> bool:
        """Legacy helper: delegates to delete_session."""
        return self.delete_session(doc_id)

    def clear_messages(self, doc_id: str) -> bool:
        """Clears messages for a session while keeping the session entry."""
        if not doc_id:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE chat_id = ? OR doc_id = ?", (doc_id, doc_id))
            conn.commit()
            return True
