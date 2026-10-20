import sys
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
BACKEND_DIR = ROOT_DIR / "backend"

for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from main import (
    app,
    vector_store,
    llm_service,
    chat_history,
    firebase_service,
    ask_question,
    upload_document,
    AskRequest,
    AskResponse,
    SequentialQuestionsRequest,
    UploadResponse
)

__all__ = [
    "app",
    "vector_store",
    "llm_service",
    "chat_history",
    "firebase_service",
    "ask_question",
    "upload_document",
    "AskRequest",
    "AskResponse",
    "SequentialQuestionsRequest",
    "UploadResponse"
]
