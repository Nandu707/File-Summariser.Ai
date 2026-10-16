import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("FirebaseService")

class FirebaseService:
    """
    Firebase integration service for File Summariser.Ai.
    Stores:
      - Uploaded raw files in Firebase Cloud Storage (or Firestore)
      - Document metadata and suggested questions in Firestore ('documents' collection)
      - Chat messages, Q&A turns, and sources in Firestore ('documents/{doc_id}/messages' or 'chat_history')
    Provides seamless fallback to SQLite / local registry if credentials are not yet supplied.
    """
    def __init__(self):
        self.is_active = False
        self.db = None
        self.bucket = None
        self._init_firebase()

    def _init_firebase(self):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore, storage

            # Don't reinitialize if already initialized
            if firebase_admin._apps:
                app = firebase_admin.get_app()
                self.db = firestore.client()
                try:
                    self.bucket = storage.bucket()
                except Exception:
                    self.bucket = None
                self.is_active = True
                print("[Firebase] Reconnected to existing Firebase Admin app.")
                return

            # Look for service account key in environment or standard file paths
            cred_path_env = os.getenv("FIREBASE_CREDENTIALS_PATH")
            cred_json_env = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
            storage_bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")

            base_dir = Path(__file__).resolve().parent.parent.parent
            possible_key_paths = [
                Path(cred_path_env) if cred_path_env else None,
                base_dir / "firebase_service_account.json",
                base_dir / "serviceAccountKey.json",
                base_dir.parent / "firebase_service_account.json",
                base_dir.parent / "serviceAccountKey.json",
            ]

            cred = None
            found_key_file = None
            for p in possible_key_paths:
                if p and p.is_file():
                    found_key_file = p
                    break

            if found_key_file:
                print(f"[Firebase] Initializing with service account file: {found_key_file}")
                cred = credentials.Certificate(str(found_key_file))
            elif cred_json_env:
                print("[Firebase] Initializing with service account JSON string from environment.")
                cert_dict = json.loads(cred_json_env)
                cred = credentials.Certificate(cert_dict)
            elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                print("[Firebase] Initializing with GOOGLE_APPLICATION_CREDENTIALS.")
                cred = credentials.ApplicationDefault()

            if cred:
                app_options = {}
                if storage_bucket_name:
                    app_options["storageBucket"] = storage_bucket_name

                firebase_admin.initialize_app(cred, app_options if app_options else None)
                self.db = firestore.client()
                try:
                    self.bucket = storage.bucket() if storage_bucket_name else None
                except Exception as b_err:
                    print(f"[Firebase] Storage bucket warning: {b_err}")
                    self.bucket = None

                self.is_active = True
                print("[Firebase] Successfully connected to Firebase Firestore & Storage!")
            else:
                print("[Firebase] Note: No Firebase credentials found. Running in hybrid local mode (Local SQLite + Registry).")
                print("[Firebase] To activate Firebase cloud storage, provide firebase_service_account.json or set FIREBASE_CREDENTIALS_PATH in .env.")
        except Exception as e:
            print(f"[Firebase] Failed to initialize Firebase: {e}")
            self.is_active = False

    # ---------------- File Storage ----------------
    def upload_file(self, doc_id: str, filename: str, content: bytes) -> Optional[str]:
        """
        Uploads file to Firebase Cloud Storage bucket.
        Returns the storage path or download URL.
        """
        if not self.is_active or not self.bucket:
            return None
        try:
            blob_path = f"documents/{doc_id}/{filename}"
            blob = self.bucket.blob(blob_path)
            blob.upload_from_string(content)
            try:
                # If public URL is supported
                blob.make_public()
                return blob.public_url
            except Exception:
                return blob_path
        except Exception as e:
            print(f"[Firebase] Error uploading file to Firebase Storage: {e}")
            return None

    # ---------------- Document Metadata & Questions ----------------
    def save_document(
        self,
        doc_id: str,
        filename: str,
        chunks: int,
        pages_count: int = 1,
        suggested_questions: Optional[List[str]] = None,
        storage_url: Optional[str] = None
    ) -> bool:
        """
        Stores document record and suggested questions in Firestore 'documents' collection.
        """
        if not self.is_active or not self.db:
            return False
        try:
            doc_ref = self.db.collection("documents").document(doc_id)
            doc_data = {
                "doc_id": doc_id,
                "filename": filename,
                "chunks": chunks,
                "pages_count": pages_count,
                "suggested_questions": suggested_questions or [],
                "storage_url": storage_url or "",
                "uploaded_at": datetime.now().isoformat(),
            }
            doc_ref.set(doc_data, merge=True)
            return True
        except Exception as e:
            print(f"[Firebase] Error saving document {doc_id} to Firestore: {e}")
            return False

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves document metadata from Firestore."""
        if not self.is_active or not self.db:
            return None
        try:
            doc_ref = self.db.collection("documents").document(doc_id)
            snapshot = doc_ref.get()
            if snapshot.exists:
                return snapshot.to_dict()
            return None
        except Exception as e:
            print(f"[Firebase] Error getting document {doc_id} from Firestore: {e}")
            return None

    def list_documents(self) -> List[Dict[str, Any]]:
        """Lists all indexed documents from Firestore."""
        if not self.is_active or not self.db:
            return []
        try:
            docs_ref = self.db.collection("documents").order_by("uploaded_at", direction="DESCENDING")
            results = []
            for doc in docs_ref.stream():
                results.append(doc.to_dict())
            return results
        except Exception as e:
            print(f"[Firebase] Error listing documents from Firestore: {e}")
            return []

    def delete_document(self, doc_id: str) -> bool:
        """Deletes document record and associated chat messages from Firestore."""
        if not self.is_active or not self.db:
            return False
        try:
            # Delete chat messages sub-collection
            chats_ref = self.db.collection("documents").document(doc_id).collection("messages")
            for msg_doc in chats_ref.stream():
                msg_doc.reference.delete()

            # Delete document record
            self.db.collection("documents").document(doc_id).delete()
            return True
        except Exception as e:
            print(f"[Firebase] Error deleting document {doc_id} from Firestore: {e}")
            return False

    # ---------------- Chat Messages Persistence ----------------
    def save_chat_message(
        self,
        doc_id: str,
        role: str,
        content: str,
        sources: Optional[List[int]] = None,
        is_error: bool = False,
        timestamp: Optional[str] = None
    ) -> Optional[str]:
        """
        Stores a chat message (user question or assistant answer) in Firestore.
        Collection: documents/{doc_id}/messages
        """
        if not self.is_active or not self.db:
            return None
        try:
            if not timestamp:
                timestamp = datetime.now().strftime("%I:%M %p")

            msg_data = {
                "doc_id": doc_id,
                "role": role,
                "content": content,
                "sources": sources or [],
                "is_error": is_error,
                "timestamp": timestamp,
                "created_at": datetime.now().isoformat()
            }
            # Auto-generated message ID
            _, msg_ref = self.db.collection("documents").document(doc_id).collection("messages").add(msg_data)
            return msg_ref.id
        except Exception as e:
            print(f"[Firebase] Error saving chat message for doc_id {doc_id} in Firestore: {e}")
            return None

    def get_chat_messages(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all chat messages for a document in chronological order from Firestore.
        """
        if not self.is_active or not self.db:
            return []
        try:
            messages_ref = (
                self.db.collection("documents")
                .document(doc_id)
                .collection("messages")
                .order_by("created_at")
            )
            messages = []
            for doc in messages_ref.stream():
                data = doc.to_dict()
                messages.append({
                    "id": doc.id,
                    "doc_id": data.get("doc_id", doc_id),
                    "role": data.get("role", "user"),
                    "content": data.get("content", ""),
                    "sources": data.get("sources", []),
                    "timestamp": data.get("timestamp", ""),
                    "time": data.get("timestamp", ""),
                    "isError": bool(data.get("is_error", False))
                })
            return messages
        except Exception as e:
            print(f"[Firebase] Error getting chat messages for {doc_id} from Firestore: {e}")
            return []

    def clear_chat_messages(self, doc_id: str) -> bool:
        """Deletes all chat messages for a specific document in Firestore."""
        if not self.is_active or not self.db:
            return False
        try:
            messages_ref = self.db.collection("documents").document(doc_id).collection("messages")
            for msg_doc in messages_ref.stream():
                msg_doc.reference.delete()
            return True
        except Exception as e:
            print(f"[Firebase] Error clearing chat messages for {doc_id} in Firestore: {e}")
            return False
