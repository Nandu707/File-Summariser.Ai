import sqlite3
import json
import os
import uuid
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta

NO_INFO_PATTERNS = [
    r"do not contain any information",
    r"does not contain any information",
    r"do not contain information",
    r"does not contain information",
    r"contain no information",
    r"contains no information",
    r"provide no information",
    r"provides no information",
    r"not in any uploaded",
    r"not in the uploaded",
    r"not available in any of the uploaded",
    r"not available in this document",
    r"not available in the uploaded",
    r"not found in the provided",
    r"not found in any of the provided",
    r"no information (?:is )?(?:found|available|provided|detailed)?.*(?:in|from) the provided",
    r"no information (?:is )?(?:found|available|provided|detailed)?.*(?:in|from) any of the",
    r"there (?:is|are) no (?:specific )?(?:information|details|mention|instructions)",
    r"(?:provided|uploaded) (?:documents?|files?|excerpts?|context) (?:do|does) not (?:contain|mention|have|provide|detail)",
    r"(?:documents?|files?|excerpts?|context) (?:do|does) not (?:contain|mention|have|provide|detail) any information",
    r"(?:documents?|files?|excerpts?|context) (?:do|does) not (?:contain|mention|have|provide|detail) information",
    r"(?:documents?|files?|excerpts?) provided (?:do|does) not (?:contain|mention|have|provide|detail)",
    r"none of the (?:provided|uploaded) (?:documents?|files?|excerpts?) (?:contain|mention|have|provide)",
    r"could not find any information",
    r"cannot find any information",
    r"based on the (?:uploaded|provided) (?:documents?|files?|excerpts?),? there (?:is|are) no",
    r"(?:does|do) not have any information",
    r"not mentioned in the (?:provided|uploaded)",
    r"cannot be answered (?:from|based on) the (?:provided|uploaded)",
]

def is_no_info_answer(answer: str) -> bool:
    """Returns True if the LLM response indicates that documents do not contain information about the question."""
    if not answer or not isinstance(answer, str):
        return False
    text = answer.strip().lower()
    for pattern in NO_INFO_PATTERNS:
        if re.search(pattern, text):
            return True
    return False

class ChatHistoryService:
    """
    SQLite persistent storage for chat sessions, messages, file statuses, and user accounts.
    Supports per-user private data isolation, full-text search, auto-titling,
    soft deletion of files, and automatic daily cleanup of old chat sessions.
    """
    def __init__(self, db_path: Optional[Path] = None, firebase_service: Optional[Any] = None):
        if db_path is None:
            if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
                tmp_dir = Path("/tmp/vector_db")
                tmp_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = tmp_dir / "chat_history.db"
            else:
                base_dir = Path(__file__).resolve().parent.parent.parent
                if (base_dir / "vector_db").exists():
                    candidate = base_dir / "vector_db" / "chat_history.db"
                elif (base_dir.parent / "vector_db").exists():
                    candidate = base_dir.parent / "vector_db" / "chat_history.db"
                else:
                    candidate = base_dir / "vector_db" / "chat_history.db"
                try:
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    test_f = candidate.parent / ".write_test"
                    test_f.touch()
                    test_f.unlink()
                    self.db_path = candidate
                except (OSError, PermissionError):
                    tmp_dir = Path("/tmp/vector_db")
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    self.db_path = tmp_dir / "chat_history.db"
        else:
            self.db_path = Path(db_path)
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError):
                tmp_dir = Path("/tmp/vector_db")
                tmp_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = tmp_dir / "chat_history.db"
        self.firebase_service = firebase_service
        self._init_db()
        self._sync_to_firebase()

    def set_firebase_service(self, firebase_service: Any):
        """Sets or updates the firebase_service instance and triggers user sync."""
        self.firebase_service = firebase_service
        self._sync_to_firebase()

    def _sync_to_firebase(self):
        """Initial background sync of existing local users to Firebase Firestore if active."""
        if not self.firebase_service or not getattr(self.firebase_service, "is_active", False):
            return
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, email, password_hash, created_at FROM users")
                users = [dict(r) for r in cursor.fetchall()]
                if users and hasattr(self.firebase_service, "sync_all_users"):
                    self.firebase_service.sync_all_users(users)
        except Exception as e:
            print(f"[ChatHistory] Notice syncing users to Firebase: {e}")

    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 0. Users table for authentication
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)
            """)

            # Migrations for users table
            user_cols = [col["name"] for col in cursor.execute("PRAGMA table_info(users)").fetchall()]
            if "role" not in user_cols:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
                except Exception:
                    pass
            if "status" not in user_cols:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
                except Exception:
                    pass

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users (status)")

            # Seed / synchronize fixed administrator account from environment variables
            self._ensure_admin_account_internal(cursor)

            # 1. Files table: tracking active/deleted status of uploaded documents
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active', -- 'active' or 'deleted'
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    user_id TEXT
                )
            """)

            # 2. Chat sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    scope TEXT NOT NULL, -- 'all' or 'file'
                    file_id TEXT,
                    file_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    user_id TEXT
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
                    source_details TEXT, -- JSON list of source objects [{file_id, file_name, page}]
                    user_id TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_doc_id ON messages (doc_id)
            """)

            # Migrations: Ensure user_id column exists on files, chat_sessions, messages
            for tbl in ["files", "chat_sessions", "messages"]:
                cols = [col["name"] for col in cursor.execute(f"PRAGMA table_info({tbl})").fetchall()]
                if "user_id" not in cols:
                    try:
                        cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id TEXT")
                    except Exception:
                        pass

            # Migrations for messages table columns
            msg_cols = [col["name"] for col in cursor.execute("PRAGMA table_info(messages)").fetchall()]
            for col_name, col_type in [
                ("chat_id", "TEXT"),
                ("filename", "TEXT"),
                ("suggested_questions", "TEXT"),
                ("source_details", "TEXT")
            ]:
                if col_name not in msg_cols:
                    try:
                        cursor.execute(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}")
                    except Exception:
                        pass

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_user ON files (user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions (user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON messages (user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)")

            # Populate chat_id from doc_id where missing
            cursor.execute("UPDATE messages SET chat_id = doc_id WHERE chat_id IS NULL OR chat_id = ''")

            # Clean up old stored messages where assistant states documents do not contain information
            try:
                cursor.execute("""
                    UPDATE messages
                    SET sources = '[]', source_details = '[]'
                    WHERE role = 'assistant' AND (
                        LOWER(content) LIKE '%do not contain%' OR
                        LOWER(content) LIKE '%does not contain%' OR
                        LOWER(content) LIKE '%contain no information%' OR
                        LOWER(content) LIKE '%not in any uploaded%' OR
                        LOWER(content) LIKE '%no information%' OR
                        LOWER(content) LIKE '%not found in the provided%'
                    )
                """)
            except Exception:
                pass

            conn.commit()

    # ==========================================
    # USER MANAGEMENT & AUTH STORAGE
    # ==========================================

    def _ensure_admin_account_internal(self, cursor):
        """
        Internal helper to synchronize the fixed administrator account from environment variables.
        Reads ADMIN_EMAIL and ADMIN_PASSWORD.
        Sets role='admin' and status='approved'.
        Enforces that all other accounts have role='user'.
        """
        admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        admin_pw = os.getenv("ADMIN_PASSWORD", "").strip()
        if not admin_email or not admin_pw:
            return

        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        pw_hash = bcrypt.hashpw(admin_pw.encode("utf-8"), salt).decode("utf-8")
        now_iso = datetime.utcnow().isoformat()

        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (admin_email,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE users 
                SET role = 'admin', status = 'approved', password_hash = ? 
                WHERE id = ?
            """, (pw_hash, existing["id"]))
        else:
            admin_id = f"user_{uuid.uuid4().hex[:12]}"
            cursor.execute("""
                INSERT INTO users (id, name, email, password_hash, role, status, created_at)
                VALUES (?, 'Administrator', ?, ?, 'admin', 'approved', ?)
            """, (admin_id, admin_email, pw_hash, now_iso))

        # Enforce exactly one admin: all other accounts get role 'user'
        cursor.execute("UPDATE users SET role = 'user' WHERE LOWER(email) != ?", (admin_email,))

    def ensure_admin_account(self, admin_email: Optional[str] = None, admin_password: Optional[str] = None):
        """Public callable method to ensure the fixed admin account exists and is approved."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if admin_email:
                os.environ["ADMIN_EMAIL"] = admin_email
            if admin_password:
                os.environ["ADMIN_PASSWORD"] = admin_password
            self._ensure_admin_account_internal(cursor)
            conn.commit()

    def create_user(self, name: str, email: str, password_hash: str) -> Dict[str, Any]:
        """
        Creates a new user record.
        All new sign-ups strictly receive role 'user' and status 'pending'.
        Client-provided roles or statuses are completely ignored.
        """
        clean_email = email.strip().lower()
        clean_name = name.strip()
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (id, name, email, password_hash, role, status, created_at)
                VALUES (?, ?, ?, ?, 'user', 'pending', ?)
            """, (user_id, clean_name, clean_email, password_hash, now_iso))
            conn.commit()

        user_dict = {
            "id": user_id,
            "name": clean_name,
            "email": clean_email,
            "password_hash": password_hash,
            "role": "user",
            "status": "pending",
            "created_at": now_iso
        }

        # Synchronize to Firebase Firestore 'users' collection if active
        if self.firebase_service and getattr(self.firebase_service, "is_active", False):
            try:
                self.firebase_service.save_user(user_dict)
            except Exception as fe:
                print(f"[ChatHistory] Notice syncing user to Firebase: {fe}")

        # Seed initial 'All files' chat session for this user
        self.create_session(scope="all", title="All files", user_id=user_id)

        return user_dict

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieves user by email address including role and status."""
        if not email:
            return None
        clean_email = email.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, email, password_hash, role, status, created_at FROM users WHERE LOWER(email) = ?", (clean_email,))
            row = cursor.fetchone()
            if row:
                return dict(row)

        # Fallback to Firebase Firestore 'users' collection
        if self.firebase_service and getattr(self.firebase_service, "is_active", False):
            try:
                fb_user = self.firebase_service.get_user_by_email(clean_email)
                if fb_user and fb_user.get("id"):
                    with self._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR IGNORE INTO users (id, name, email, password_hash, role, status, created_at)
                            VALUES (?, ?, ?, ?, 'user', 'pending', ?)
                        """, (
                            fb_user["id"],
                            fb_user.get("name", ""),
                            fb_user.get("email", clean_email),
                            fb_user.get("password_hash", ""),
                            fb_user.get("created_at", datetime.utcnow().isoformat())
                        ))
                        conn.commit()
                    return fb_user
            except Exception as fe:
                print(f"[ChatHistory] Notice fetching user from Firebase by email: {fe}")

        return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves user by user ID including role and status."""
        if not user_id:
            return None
        clean_id = user_id.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, email, password_hash, role, status, created_at FROM users WHERE id = ?", (clean_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

        return None

    def list_all_users(self) -> List[Dict[str, Any]]:
        """Returns all registered users for the admin dashboard, ordered by sign-up date."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, email, role, status, created_at 
                FROM users 
                ORDER BY created_at DESC
            """)
            return [dict(r) for r in cursor.fetchall()]

    def update_user_status(self, user_id: str, new_status: str) -> bool:
        """Updates user status (pending, approved, rejected, disabled)."""
        valid_statuses = {"pending", "approved", "rejected", "disabled"}
        if new_status not in valid_statuses:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id.strip()))
            conn.commit()
            return cursor.rowcount > 0

    def delete_user(self, user_id: str) -> bool:
        """
        Deletes a user account and removes all their chat sessions and messages.
        Does NOT delete any files or accounts of other users.
        """
        clean_uid = user_id.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE user_id = ?", (clean_uid,))
            cursor.execute("DELETE FROM chat_sessions WHERE user_id = ?", (clean_uid,))
            cursor.execute("DELETE FROM users WHERE id = ?", (clean_uid,))
            conn.commit()
            return cursor.rowcount > 0

    # ==========================================
    # FILE MANAGEMENT (STATUS TRACKING & SOFT DELETION)
    # ==========================================

    def register_file(
        self,
        file_id: Optional[str] = None,
        name: Optional[str] = None,
        status: str = "active",
        user_id: Optional[str] = None,
        doc_id: Optional[str] = None,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers or updates a file status in the SQLite DB, tied to user_id."""
        actual_id = file_id or doc_id
        if not actual_id:
            return {}
        clean_id = str(actual_id).strip()
        clean_name = name or filename or "Document"
        now_iso = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, status, user_id FROM files WHERE id = ?", (clean_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE files SET name = ?, status = ?, deleted_at = NULL, user_id = COALESCE(?, user_id) WHERE id = ?
                """, (clean_name, status, user_id, clean_id))
            else:
                cursor.execute("""
                    INSERT INTO files (id, name, status, created_at, deleted_at, user_id)
                    VALUES (?, ?, ?, ?, NULL, ?)
                """, (clean_id, clean_name, status, now_iso, user_id))
            conn.commit()
            return {"id": clean_id, "name": clean_name, "status": status, "user_id": user_id}

    def mark_file_deleted(self, file_id: str, user_id: Optional[str] = None) -> bool:
        """
        Marks a file as 'deleted' for the given user.
        Preserves all chat sessions and messages for this file and copies the file name
        so chats remain viewable and marked 'File deleted' (read-only).
        """
        if not file_id or file_id == "all":
            return False
        clean_id = file_id.strip()
        now_iso = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT name, user_id FROM files WHERE id = ?"
            params = [clean_id]
            if user_id:
                query += " AND (user_id = ? OR user_id IS NULL)"
                params.append(user_id)
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE files SET status = 'deleted', deleted_at = ? WHERE id = ?
                """, (now_iso, clean_id))
            else:
                cursor.execute("SELECT file_name FROM chat_sessions WHERE file_id = ? LIMIT 1", (clean_id,))
                s_row = cursor.fetchone()
                fn = s_row["file_name"] if s_row and s_row["file_name"] else "Deleted Document"
                cursor.execute("""
                    INSERT INTO files (id, name, status, created_at, deleted_at, user_id)
                    VALUES (?, ?, 'deleted', ?, ?, ?)
                """, (clean_id, fn, now_iso, now_iso, user_id))

            cursor.execute("""
                UPDATE threads SET is_deleted = 1, deleted_at = ? WHERE doc_id = ?
            """, (now_iso, clean_id))

            conn.commit()
            return True

    def is_file_deleted(self, file_id: Optional[str], user_id: Optional[str] = None) -> bool:
        """Checks if a file is marked as deleted, respecting user_id."""
        if not file_id or file_id == "all":
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT status, user_id FROM files WHERE id = ?"
            params = [file_id.strip()]
            if user_id:
                query += " AND (user_id = ? OR user_id IS NULL)"
                params.append(user_id)
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row:
                return row["status"] == "deleted"
            cursor.execute("SELECT is_deleted FROM threads WHERE doc_id = ?", (file_id.strip(),))
            t_row = cursor.fetchone()
            return bool(t_row and t_row["is_deleted"])

    def get_active_file_ids(self, user_id: Optional[str] = None) -> Set[str]:
        """Returns set of all file IDs that are currently active for the given user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT id FROM files WHERE status = 'active' AND (user_id = ? OR user_id IS NULL)", (user_id,))
            else:
                cursor.execute("SELECT id FROM files WHERE status = 'active'")
            return {r["id"] for r in cursor.fetchall()}

    def get_file(self, file_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Returns file record if owned by user_id."""
        if not file_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, name, status, created_at, deleted_at, user_id FROM files WHERE id = ?"
            params = [file_id]
            if user_id:
                query += " AND (user_id = ? OR user_id IS NULL)"
                params.append(user_id)
            cursor.execute(query, params)
            r = cursor.fetchone()
            if r:
                return dict(r)
            return None

    # ==========================================
    # CHAT SESSION MANAGEMENT
    # ==========================================

    def create_session(
        self,
        scope: Optional[str] = None,
        file_id: Optional[str] = None,
        file_name: Optional[str] = None,
        title: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new chat session.
        Scope can be 'all' or 'file', or inferred from doc_id.
        Tied strictly to user_id.
        """
        if doc_id:
            if doc_id in ("all", "*"):
                clean_scope = "all"
                clean_file_id = None
            else:
                clean_scope = "file"
                clean_file_id = doc_id.strip()
        else:
            clean_scope = "file" if scope == "file" else "all"
            clean_file_id = file_id.strip() if file_id and clean_scope == "file" else None

        clean_fn = file_name.strip() if file_name else ("All files" if clean_scope == "all" else "Document")
        clean_title = title.strip() if title else ("All files" if clean_scope == "all" else f"Chat: {clean_fn}")

        actual_session_id = session_id if session_id else f"chat_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_sessions (id, title, scope, file_id, file_name, created_at, updated_at, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (actual_session_id, clean_title, clean_scope, clean_file_id, clean_fn, now_iso, now_iso, user_id))
            conn.commit()

        session_dict = {
            "id": actual_session_id,
            "title": clean_title,
            "scope": clean_scope,
            "file_id": clean_file_id,
            "file_name": clean_fn,
            "is_file_deleted": self.is_file_deleted(clean_file_id, user_id=user_id),
            "created_at": now_iso,
            "updated_at": now_iso,
            "user_id": user_id,
            "message_count": 0
        }

        # Synchronize session to Firebase Firestore
        if self.firebase_service and getattr(self.firebase_service, "is_active", False):
            try:
                self.firebase_service.save_session(session_dict)
            except Exception as fe:
                print(f"[ChatHistory] Notice syncing session to Firebase: {fe}")

        return session_dict

    def get_session(self, chat_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves session details by id, strictly verifying ownership by user_id."""
        if not chat_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.title, s.scope, s.file_id, s.file_name, s.created_at, s.updated_at, s.user_id,
                       COUNT(m.id) as message_count
                FROM chat_sessions s
                LEFT JOIN messages m ON s.id = m.chat_id
                WHERE s.id = ?
                GROUP BY s.id
            """, (chat_id,))
            r = cursor.fetchone()
            if not r:
                return None

            # Strict ownership check: if user_id is provided, session must belong to user_id
            if user_id:
                session_owner = r["user_id"]
                if not session_owner or session_owner != str(user_id):
                    return None

            is_deleted = self.is_file_deleted(r["file_id"], user_id=user_id) if r["scope"] == "file" else False
            return {
                "id": r["id"],
                "title": r["title"],
                "scope": r["scope"],
                "file_id": r["file_id"],
                "file_name": r["file_name"],
                "is_file_deleted": is_deleted,
                "is_deleted": is_deleted,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "user_id": r["user_id"],
                "message_count": r["message_count"]
            }

    def get_sessions(
        self,
        arg1: Optional[str] = None,
        arg2: Optional[str] = None,
        user_id: Optional[str] = None,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all chat sessions for the logged-in user, ordered by updated_at DESC (newest first).
        Strictly isolated by user_id. Handles positional or keyword invocations transparently.
        When search_query is supplied, filters by title AND message content text.
        """
        # Resolve user_id and search_query flexibly
        effective_user_id = user_id
        effective_query = search_query

        if effective_user_id is None and effective_query is None:
            # Check positional arguments
            if arg1 and (arg1.startswith("user_") or "@" in arg1):
                effective_user_id = arg1
                effective_query = arg2
            elif arg2 and (arg2.startswith("user_") or "@" in arg2):
                effective_user_id = arg2
                effective_query = arg1
            else:
                effective_user_id = arg1
                effective_query = arg2

        clean_q = effective_query.strip().lower() if effective_query else ""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT s.id, s.title, s.scope, s.file_id, s.file_name, s.created_at, s.updated_at, s.user_id,
                       COUNT(m.id) as message_count,
                       MAX(m.id) as last_msg_id
                FROM chat_sessions s
                LEFT JOIN messages m ON s.id = m.chat_id
            """
            where_clauses = []
            params = []

            if effective_user_id:
                where_clauses.append("s.user_id = ?")
                params.append(effective_user_id)

            if clean_q:
                where_clauses.append("""
                    (LOWER(s.title) LIKE ?
                     OR s.id IN (
                         SELECT chat_id FROM messages
                         WHERE LOWER(content) LIKE ? AND (? IS NULL OR user_id = ?)
                     ))
                """)
                like_term = f"%{clean_q}%"
                params.extend([like_term, like_term, effective_user_id, effective_user_id])

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

            query += """
                GROUP BY s.id
                HAVING COUNT(m.id) > 0 OR s.id = (
                    SELECT id FROM chat_sessions 
                    WHERE (? IS NULL OR user_id = ?) 
                    ORDER BY updated_at DESC LIMIT 1
                )
                ORDER BY s.updated_at DESC
            """
            cursor.execute(query, params + [effective_user_id, effective_user_id])
            rows = cursor.fetchall()

            # If user has 0 sessions, automatically create a default "All files" session
            if user_id and len(rows) == 0 and not clean_q:
                now_iso = datetime.utcnow().isoformat()
                new_id = f"chat_{uuid.uuid4().hex[:12]}"
                cursor.execute("""
                    INSERT INTO chat_sessions (id, title, scope, file_id, file_name, created_at, updated_at, user_id)
                    VALUES (?, 'All files', 'all', NULL, 'All files', ?, ?, ?)
                """, (new_id, now_iso, now_iso, user_id))
                conn.commit()
                return [{
                    "id": new_id,
                    "title": "All files",
                    "scope": "all",
                    "file_id": None,
                    "file_name": "All files",
                    "is_file_deleted": False,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "user_id": user_id,
                    "message_count": 0
                }]

            result = []
            for r in rows:
                is_deleted = self.is_file_deleted(r["file_id"], user_id=user_id) if r["scope"] == "file" else False
                result.append({
                    "id": r["id"],
                    "title": r["title"],
                    "scope": r["scope"],
                    "file_id": r["file_id"],
                    "file_name": r["file_name"] or ("All files" if r["scope"] == "all" else "Document"),
                    "is_file_deleted": is_deleted,
                    "is_deleted": is_deleted,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "user_id": r["user_id"],
                    "message_count": r["message_count"]
                })
            return result

    def update_session_title(self, chat_id: str, title: str, user_id: Optional[str] = None) -> bool:
        """Renames a chat session if owned by user_id."""
        if not chat_id or not title:
            return False
        if user_id:
            sess = self.get_session(chat_id, user_id=user_id)
            if not sess:
                return False
        clean_title = title.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE chat_sessions SET title = ? WHERE id = ?
            """, (clean_title, chat_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_session(
        self,
        chat_id: str,
        title: Optional[str] = None,
        scope: Optional[str] = None,
        file_id: Optional[str] = None,
        file_name: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """Updates a chat session's title, scope, and file details if owned by user_id."""
        if not chat_id:
            return False
        if user_id:
            sess = self.get_session(chat_id, user_id=user_id)
            if not sess:
                return False

        fields = []
        params = []
        if title is not None:
            fields.append("title = ?")
            params.append(title.strip())
        if scope is not None:
            fields.append("scope = ?")
            params.append(scope.strip())
            if scope.strip() == "all":
                fields.append("file_id = NULL")
                fields.append("file_name = NULL")
        if scope != "all":
            if file_id is not None:
                fields.append("file_id = ?")
                params.append(file_id.strip() if file_id else None)
            if file_name is not None:
                fields.append("file_name = ?")
                params.append(file_name.strip() if file_name else None)

        if not fields:
            return False

        fields.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())

        params.append(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = f"UPDATE chat_sessions SET {', '.join(fields)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def touch_session(self, chat_id: str, updated_at: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """Updates the updated_at timestamp of a chat session so it moves to top of list."""
        if not chat_id:
            return False
        now_iso = updated_at or datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "UPDATE chat_sessions SET updated_at = ? WHERE id = ?"
            params = [now_iso, chat_id]
            if user_id:
                query += " AND (user_id = ? OR user_id IS NULL)"
                params.append(user_id)
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_session(self, chat_id: str, user_id: Optional[str] = None) -> bool:
        """
        Permanently deletes only that chat session and all its messages.
        Enforces user ownership check.
        """
        if not chat_id:
            return False
        if user_id:
            sess = self.get_session(chat_id, user_id=user_id)
            if not sess:
                return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("DELETE FROM messages WHERE (chat_id = ? OR (chat_id IS NULL AND doc_id = ?)) AND (user_id = ? OR user_id IS NULL)", (chat_id, chat_id, user_id))
                cursor.execute("DELETE FROM chat_sessions WHERE id = ? AND (user_id = ? OR user_id IS NULL)", (chat_id, user_id))
            else:
                cursor.execute("DELETE FROM messages WHERE chat_id = ? OR (chat_id IS NULL AND doc_id = ?)", (chat_id, chat_id))
                cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (chat_id,))
            if chat_id != "all":
                cursor.execute("DELETE FROM threads WHERE doc_id = ?", (chat_id,))
            conn.commit()

        if self.firebase_service and getattr(self.firebase_service, "is_active", False):
            try:
                self.firebase_service.delete_session(chat_id)
            except Exception as fe:
                print(f"[ChatHistory] Notice deleting session from Firebase: {fe}")

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
        source_details: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None
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
        session = self.get_session(clean_chat_id, user_id=user_id)
        if not session:
            scope = "all" if clean_doc_id == "all" else "file"
            file_id = None if scope == "all" else clean_doc_id
            self.create_session(scope=scope, file_id=file_id, file_name=filename, title=filename or "New chat", user_id=user_id)
            session = self.get_session(clean_chat_id, user_id=user_id)

        # Auto-title from first user question if title is still default "New chat"
        if role == "user" and session:
            current_title = (session.get("title") or "").strip()
            if current_title in ("New chat", "All files", "Document") or current_title.startswith("Chat: "):
                clean_q = content.strip().replace("\n", " ")
                if len(clean_q) > 42:
                    new_title = clean_q[:40].rstrip() + "..."
                else:
                    new_title = clean_q
                if new_title:
                    self.update_session_title(clean_chat_id, new_title, user_id=user_id)

        if role == "assistant" and is_no_info_answer(content):
            sources = []
            source_details = []

        sources_json = json.dumps(sources or [])
        seq_questions_json = json.dumps(suggested_questions or []) if suggested_questions else "[]"
        source_details_json = json.dumps(source_details or []) if source_details else "[]"
        clean_fn = filename or (session.get("file_name") if session else None) or "Document"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (chat_id, doc_id, filename, role, content, sources, timestamp, is_error, suggested_questions, source_details, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (clean_chat_id, clean_doc_id, clean_fn, role, content, sources_json, timestamp, 1 if is_error else 0, seq_questions_json, source_details_json, user_id))
            msg_id = cursor.lastrowid

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
                "isError": is_error,
                "user_id": user_id
            }

    def get_messages(self, chat_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves all chat messages for a chat session in chronological order.
        Strictly verifies ownership by user_id.
        """
        if not chat_id:
            return []
        if user_id:
            sess = self.get_session(chat_id, user_id=user_id)
            if not sess:
                # chat_id might be a file_id
                file_rec = self.get_file(chat_id, user_id=user_id)
                if not file_rec and chat_id != "all":
                    return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, chat_id, doc_id, filename, role, content, sources, timestamp, is_error, suggested_questions, source_details, user_id
                FROM messages
                WHERE (chat_id = ? OR (chat_id IS NULL AND doc_id = ?) OR doc_id = ?)
            """
            params = [chat_id, chat_id, chat_id]
            if user_id:
                query += " AND (user_id = ? OR user_id IS NULL)"
                params.append(user_id)
            query += " ORDER BY id ASC"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Pre-fetch deleted file IDs to enrich source tags
            deleted_ids = set()
            try:
                if user_id:
                    cursor.execute("SELECT id FROM files WHERE status = 'deleted' AND (user_id = ? OR user_id IS NULL)", (user_id,))
                else:
                    cursor.execute("SELECT id FROM files WHERE status = 'deleted'")
                deleted_ids = {r["id"] for r in cursor.fetchall()}
            except Exception:
                pass

            messages = []
            for r in rows:
                try:
                    sources = json.loads(r["sources"]) if r["sources"] else []
                except Exception:
                    sources = []

                try:
                    seq_q = json.loads(r["suggested_questions"]) if r["suggested_questions"] else []
                except Exception:
                    seq_q = []

                try:
                    src_details = json.loads(r["source_details"]) if r["source_details"] else []
                except Exception:
                    src_details = []

                enriched_details = []
                for sd in src_details:
                    sd_copy = dict(sd)
                    fid = sd_copy.get("file_id") or sd_copy.get("doc_id")
                    sd_copy["is_deleted"] = bool(fid in deleted_ids)
                    enriched_details.append(sd_copy)

                is_no_info = (r["role"] == "assistant" and is_no_info_answer(r["content"]))
                final_sources = [] if is_no_info else sources
                final_details = [] if is_no_info else enriched_details

                messages.append({
                    "id": r["id"],
                    "chat_id": r["chat_id"],
                    "doc_id": r["doc_id"],
                    "filename": r["filename"],
                    "role": r["role"],
                    "content": r["content"],
                    "text": r["content"],
                    "sources": final_sources,
                    "source_details": final_details,
                    "suggested_questions": seq_q,
                    "timestamp": r["timestamp"],
                    "time": r["timestamp"],
                    "is_error": bool(r["is_error"]),
                    "isError": bool(r["is_error"]),
                    "user_id": r["user_id"]
                })
            return messages

    def delete_message_turn(
        self,
        chat_id: str,
        message_id: int,
        user_id: Optional[str] = None,
        truncate: bool = False
    ) -> bool:
        """
        Deletes a user question and its related Q&A response from a chat session.
        If truncate=True, deletes all messages from this message_id onwards in this chat.
        If truncate=False, deletes just this message and its immediate assistant answer (if any).
        Strictly verifies user ownership.
        """
        clean_chat_id = (chat_id or "").strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, role, chat_id, doc_id, user_id FROM messages WHERE id = ?", (message_id,))
            row = cursor.fetchone()
            if not row:
                return False

            if user_id and row["user_id"] and str(row["user_id"]) != str(user_id):
                return False

            target_chat_id = clean_chat_id or row["chat_id"] or row["doc_id"]

            if truncate:
                if user_id:
                    cursor.execute("""
                        DELETE FROM messages 
                        WHERE (chat_id = ? OR doc_id = ?) 
                          AND id >= ? 
                          AND (user_id = ? OR user_id IS NULL)
                    """, (target_chat_id, target_chat_id, message_id, user_id))
                else:
                    cursor.execute("""
                        DELETE FROM messages 
                        WHERE (chat_id = ? OR doc_id = ?) 
                          AND id >= ?
                    """, (target_chat_id, target_chat_id, message_id))
            else:
                ids_to_delete = [message_id]
                if row["role"] == "user":
                    cursor.execute("""
                        SELECT id FROM messages 
                        WHERE (chat_id = ? OR doc_id = ?) 
                          AND id > ? 
                          AND role = 'assistant'
                        ORDER BY id ASC LIMIT 1
                    """, (target_chat_id, target_chat_id, message_id))
                    next_row = cursor.fetchone()
                    if next_row:
                        ids_to_delete.append(next_row["id"])

                placeholders = ",".join("?" for _ in ids_to_delete)
                cursor.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids_to_delete)

            now_iso = datetime.utcnow().isoformat()
            cursor.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now_iso, target_chat_id))

            conn.commit()
            return True

    def get_safe_history_for_llm(
        self,
        chat_id: str,
        active_file_ids: Set[str],
        user_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Retrieves conversational history safe for inclusion in LLM prompt context.
        Excludes any turns based on deleted files. Verifies ownership.
        """
        all_msgs = self.get_messages(chat_id, user_id=user_id)
        if not all_msgs:
            return []

        safe_turns = []
        pending_user_msg = None

        for m in all_msgs:
            if m["role"] == "user":
                pending_user_msg = m["content"]
            elif m["role"] == "assistant":
                details = m.get("source_details", [])
                used_file_ids = set()
                for d in details:
                    fid = d.get("file_id") or d.get("doc_id")
                    if fid and fid != "all":
                        used_file_ids.add(fid)

                has_deleted_dependency = any(fid not in active_file_ids for fid in used_file_ids)

                if not has_deleted_dependency:
                    if pending_user_msg:
                        safe_turns.append({"role": "user", "content": pending_user_msg})
                    safe_turns.append({"role": "assistant", "content": m["content"]})

                pending_user_msg = None

        return safe_turns

    # ==========================================
    # AUTOMATIC CHAT CLEANUP
    # ==========================================

    def cleanup_old_chats(self, retention_days: int = 30) -> int:
        """
        Permanently deletes chats, with their messages, whose updated_at is older
        than the retention period. Runs for all users without needing anyone to be logged in.
        It deletes chats only. It NEVER deletes a user's active files or account.
        Ensures affected users have a fresh empty 'All files' chat ready.
        Logs count of deleted chats with NO message content in logs.
        """
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id FROM chat_sessions
                WHERE updated_at < ? OR (updated_at IS NULL AND created_at < ?)
            """, (cutoff, cutoff))
            expired = cursor.fetchall()
            if not expired:
                print(f"[ChatCleanup] Zero chats older than {retention_days} days found.")
                return 0

            expired_ids = [r["id"] for r in expired]
            affected_users = set(r["user_id"] for r in expired if r["user_id"])

            for sid in expired_ids:
                cursor.execute("DELETE FROM messages WHERE chat_id = ? OR doc_id = ?", (sid, sid))
                cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (sid,))
            conn.commit()

            # Ensure every affected user still has an empty 'All files' session
            for uid in affected_users:
                cursor.execute("SELECT COUNT(*) as cnt FROM chat_sessions WHERE user_id = ?", (uid,))
                row = cursor.fetchone()
                if not row or row["cnt"] == 0:
                    now_iso = datetime.utcnow().isoformat()
                    new_id = f"chat_{uuid.uuid4().hex[:12]}"
                    cursor.execute("""
                        INSERT INTO chat_sessions (id, title, scope, file_id, file_name, created_at, updated_at, user_id)
                        VALUES (?, 'All files', 'all', NULL, 'All files', ?, ?, ?)
                    """, (new_id, now_iso, now_iso, uid))
            conn.commit()

            deleted_count = len(expired_ids)
            print(f"[ChatCleanup] Successfully cleaned up {deleted_count} chats older than {retention_days} days.")
            return deleted_count

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

    def get_threads(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Legacy helper: returns chat sessions mapped to thread structure for user_id."""
        sessions = self.get_sessions(user_id=user_id)
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

    def delete_thread(self, doc_id: str, user_id: Optional[str] = None) -> bool:
        """Legacy helper: delegates to delete_session with user_id."""
        return self.delete_session(doc_id, user_id=user_id)

    def clear_messages(self, doc_id: str, user_id: Optional[str] = None) -> bool:
        """Clears messages for a session while keeping the session entry, isolated by user_id."""
        if not doc_id:
            return False
        if user_id:
            sess = self.get_session(doc_id, user_id=user_id)
            if not sess and doc_id != "all":
                file_rec = self.get_file(doc_id, user_id=user_id)
                if not file_rec:
                    return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "DELETE FROM messages WHERE (chat_id = ? OR doc_id = ?)"
            params = [doc_id, doc_id]
            if user_id:
                query += " AND (user_id = ? OR user_id IS NULL)"
                params.append(user_id)
            cursor.execute(query, params)
            conn.commit()
            return True
