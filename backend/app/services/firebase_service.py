import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import requests

logger = logging.getLogger("FirebaseService")

def _to_firestore_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Converts a standard Python dictionary to Firestore REST typed fields."""
    def _to_val(v):
        if isinstance(v, bool):
            return {"booleanValue": v}
        elif isinstance(v, int):
            return {"integerValue": str(v)}
        elif isinstance(v, float):
            return {"doubleValue": v}
        elif isinstance(v, str):
            return {"stringValue": v}
        elif isinstance(v, list):
            return {"arrayValue": {"values": [_to_val(x) for x in v]}}
        elif isinstance(v, dict):
            return {"mapValue": {"fields": {k: _to_val(x) for k, x in v.items()}}}
        return {"nullValue": None}
    return {k: _to_val(v) for k, v in data.items()}

def _from_firestore_fields(fields_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Converts Firestore REST typed fields back to standard Python types."""
    def _from_val(val_dict):
        if not isinstance(val_dict, dict):
            return val_dict
        if "stringValue" in val_dict:
            return val_dict["stringValue"]
        if "integerValue" in val_dict:
            return int(val_dict["integerValue"])
        if "doubleValue" in val_dict:
            return float(val_dict["doubleValue"])
        if "booleanValue" in val_dict:
            return val_dict["booleanValue"]
        if "arrayValue" in val_dict:
            return [_from_val(x) for x in val_dict["arrayValue"].get("values", [])]
        if "mapValue" in val_dict:
            return {k: _from_val(v) for k, v in val_dict["mapValue"].get("fields", {}).items()}
        if "nullValue" in val_dict:
            return None
        return str(val_dict)
    return {k: _from_val(v) for k, v in fields_dict.items()}


class FirebaseService:
    """
    Firebase integration service for File Summariser.Ai.
    Supports both:
      1. Direct Firebase REST API (with FIREBASE_PROJECT_ID & FIREBASE_API_KEY)
      2. Firebase Admin SDK (with serviceAccount.json certificate)
    Stores:
      - Uploaded raw files in Firebase Cloud Storage
      - Document metadata and suggested questions in Firestore ('documents' collection)
      - Chat messages, Q&A turns, and citations in Firestore ('documents/{doc_id}/messages')
    Provides seamless fallback to SQLite / local registry if Firebase is not yet enabled.
    """
    def __init__(self):
        self.is_active = False
        self.mode = "none" # "admin" | "rest" | "none"
        self.db = None
        self.bucket = None
        
        self.api_key = os.getenv("FIREBASE_API_KEY", "").strip()
        self.project_id = os.getenv("FIREBASE_PROJECT_ID", "file-summariser-ai").strip()
        self.storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET", f"{self.project_id}.firebasestorage.app").strip()

        self.firestore_base_url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents"
        self.storage_base_url = f"https://firebasestorage.googleapis.com/v0/b/{self.storage_bucket}/o"

        self._init_firebase()

    def _init_firebase(self):
        # 1. Try Firebase Admin SDK if key file exists
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore, storage

            if firebase_admin._apps:
                self.db = firestore.client()
                try:
                    self.bucket = storage.bucket()
                except Exception:
                    self.bucket = None
                self.is_active = True
                self.mode = "admin"
                print("[Firebase] Reconnected to Firebase Admin App.")
                return

            base_dir = Path(__file__).resolve().parent.parent.parent
            possible_key_paths = [
                Path(os.getenv("FIREBASE_CREDENTIALS_PATH", "")) if os.getenv("FIREBASE_CREDENTIALS_PATH") else None,
                base_dir / "firebase_service_account.json",
                base_dir / "serviceAccountKey.json",
                base_dir.parent / "firebase_service_account.json",
                base_dir.parent / "serviceAccountKey.json",
            ]

            found_key_file = next((p for p in possible_key_paths if p and p.is_file()), None)

            if found_key_file:
                print(f"[Firebase] Initializing Firebase Admin with service account: {found_key_file}")
                cred = credentials.Certificate(str(found_key_file))
                firebase_admin.initialize_app(cred, {"storageBucket": self.storage_bucket})
                self.db = firestore.client()
                self.bucket = storage.bucket()
                self.is_active = True
                self.mode = "admin"
                print("[Firebase] Successfully connected via Firebase Admin SDK!")
                return
        except Exception as e:
            print(f"[Firebase] Admin SDK init notice: {e}")

        # 2. Use Direct Firebase REST API if Project ID and API Key exist
        if self.project_id and self.api_key:
            self.is_active = True
            self.mode = "rest"
            print(f"[Firebase] Connected via Firebase REST API for Project: '{self.project_id}'")
            return

        print("[Firebase] Running in local SQLite mode (Firebase credentials not supplied).")

    # ---------------- File Storage ----------------
    def upload_file(self, doc_id: str, filename: str, content: bytes) -> Optional[str]:
        """
        Uploads file to Firebase Cloud Storage bucket.
        """
        if not self.is_active:
            return None

        # Admin SDK Mode
        if self.mode == "admin" and self.bucket:
            try:
                blob_path = f"documents/{doc_id}/{filename}"
                blob = self.bucket.blob(blob_path)
                blob.upload_from_string(content)
                return blob_path
            except Exception as e:
                print(f"[Firebase] Admin storage upload error: {e}")

        # REST API Mode
        if self.mode == "rest" and self.api_key and self.storage_bucket:
            try:
                blob_path = f"documents/{doc_id}/{filename}"
                url = f"{self.storage_base_url}?uploadType=media&name={blob_path}&key={self.api_key}"
                r = requests.post(url, data=content, headers={"Content-Type": "application/octet-stream"}, timeout=15)
                if r.status_code in [200, 201]:
                    return f"gs://{self.storage_bucket}/{blob_path}"
                else:
                    print(f"[Firebase Storage REST] Status {r.status_code}: {r.text[:120]}")
            except Exception as e:
                print(f"[Firebase] Storage REST error: {e}")

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
        if not self.is_active:
            return False

        doc_data = {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": chunks,
            "pages_count": pages_count,
            "suggested_questions": suggested_questions or [],
            "storage_url": storage_url or "",
            "uploaded_at": datetime.utcnow().isoformat(),
        }

        # Admin SDK Mode
        if self.mode == "admin" and self.db:
            try:
                self.db.collection("documents").document(doc_id).set(doc_data, merge=True)
                return True
            except Exception as e:
                print(f"[Firebase Admin] Error saving document {doc_id}: {e}")

        # REST API Mode
        if self.mode == "rest" and self.api_key:
            try:
                url = f"{self.firestore_base_url}/documents/{doc_id}?key={self.api_key}"
                body = {"fields": _to_firestore_fields(doc_data)}
                r = requests.patch(url, json=body, timeout=10)
                if r.status_code in [200, 201]:
                    return True
                else:
                    print(f"[Firebase Firestore REST] Save document status {r.status_code}: {r.text[:150]}")
            except Exception as e:
                print(f"[Firebase REST] Error saving document {doc_id}: {e}")

        return False

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves document metadata from Firestore."""
        if not self.is_active:
            return None

        # Admin SDK Mode
        if self.mode == "admin" and self.db:
            try:
                snap = self.db.collection("documents").document(doc_id).get()
                return snap.to_dict() if snap.exists else None
            except Exception as e:
                print(f"[Firebase Admin] Error getting document {doc_id}: {e}")

        # REST API Mode
        if self.mode == "rest" and self.api_key:
            try:
                url = f"{self.firestore_base_url}/documents/{doc_id}?key={self.api_key}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    return _from_firestore_fields(data.get("fields", {}))
            except Exception as e:
                print(f"[Firebase REST] Error getting document {doc_id}: {e}")

        return None

    def delete_document(self, doc_id: str) -> bool:
        """Deletes document record from Firestore."""
        if not self.is_active:
            return False

        # Admin SDK Mode
        if self.mode == "admin" and self.db:
            try:
                self.clear_chat_messages(doc_id)
                self.db.collection("documents").document(doc_id).delete()
                return True
            except Exception:
                pass

        # REST API Mode
        if self.mode == "rest" and self.api_key:
            try:
                self.clear_chat_messages(doc_id)
                url = f"{self.firestore_base_url}/documents/{doc_id}?key={self.api_key}"
                requests.delete(url, timeout=10)
                return True
            except Exception as e:
                print(f"[Firebase REST] Error deleting document {doc_id}: {e}")

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
        Collection path: documents/{doc_id}/messages
        """
        if not self.is_active:
            return None

        if not timestamp:
            timestamp = datetime.now().strftime("%I:%M %p")

        msg_data = {
            "doc_id": doc_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "is_error": is_error,
            "timestamp": timestamp,
            "created_at": datetime.utcnow().isoformat()
        }

        # Admin SDK Mode
        if self.mode == "admin" and self.db:
            try:
                _, msg_ref = self.db.collection("documents").document(doc_id).collection("messages").add(msg_data)
                return msg_ref.id
            except Exception as e:
                print(f"[Firebase Admin] Error saving message: {e}")

        # REST API Mode
        if self.mode == "rest" and self.api_key:
            try:
                url = f"{self.firestore_base_url}/documents/{doc_id}/messages?key={self.api_key}"
                body = {"fields": _to_firestore_fields(msg_data)}
                r = requests.post(url, json=body, timeout=10)
                if r.status_code in [200, 201]:
                    res_json = r.json()
                    name = res_json.get("name", "")
                    return name.split("/")[-1] if name else "id"
                else:
                    print(f"[Firebase Firestore REST] Save message status {r.status_code}: {r.text[:120]}")
            except Exception as e:
                print(f"[Firebase REST] Error saving message: {e}")

        return None

    def get_chat_messages(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all chat messages for a document in chronological order from Firestore.
        """
        if not self.is_active:
            return []

        # Admin SDK Mode
        if self.mode == "admin" and self.db:
            try:
                messages_ref = self.db.collection("documents").document(doc_id).collection("messages").order_by("created_at")
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
                print(f"[Firebase Admin] Error getting messages: {e}")

        # REST API Mode
        if self.mode == "rest" and self.api_key:
            try:
                url = f"{self.firestore_base_url}/documents/{doc_id}/messages?key={self.api_key}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    docs = data.get("documents", [])
                    messages = []
                    for d in docs:
                        fields = _from_firestore_fields(d.get("fields", {}))
                        name = d.get("name", "")
                        msg_id = name.split("/")[-1] if name else "id"
                        messages.append({
                            "id": msg_id,
                            "doc_id": fields.get("doc_id", doc_id),
                            "role": fields.get("role", "user"),
                            "content": fields.get("content", ""),
                            "sources": fields.get("sources", []),
                            "timestamp": fields.get("timestamp", ""),
                            "time": fields.get("timestamp", ""),
                            "isError": bool(fields.get("is_error", False)),
                            "created_at": fields.get("created_at", "")
                        })
                    messages.sort(key=lambda x: x.get("created_at", ""))
                    return messages
                elif r.status_code == 404:
                    return []
                else:
                    print(f"[Firebase Firestore REST] Get messages status {r.status_code}: {r.text[:120]}")
            except Exception as e:
                print(f"[Firebase REST] Error getting messages: {e}")

        return []

    def clear_chat_messages(self, doc_id: str) -> bool:
        """Deletes all chat messages for a document in Firestore."""
        if not self.is_active:
            return False

        # Admin SDK Mode
        if self.mode == "admin" and self.db:
            try:
                messages_ref = self.db.collection("documents").document(doc_id).collection("messages")
                for msg_doc in messages_ref.stream():
                    msg_doc.reference.delete()
                return True
            except Exception as e:
                print(f"[Firebase Admin] Error clearing messages: {e}")

        # REST API Mode
        if self.mode == "rest" and self.api_key:
            try:
                url = f"{self.firestore_base_url}/documents/{doc_id}/messages?key={self.api_key}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    for d in data.get("documents", []):
                        doc_name = d.get("name")
                        if doc_name:
                            del_url = f"https://firestore.googleapis.com/v1/{doc_name}?key={self.api_key}"
                            requests.delete(del_url, timeout=5)
                return True
            except Exception as e:
                print(f"[Firebase REST] Error clearing messages: {e}")

        return False
