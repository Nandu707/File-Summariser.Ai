import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ensure backend directory and its app folder are in sys.path
current_dir = Path(__file__).resolve().parent.parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from app.services.vector_store import VectorStoreService
    from app.services.llm_service import LLMService
    from app.services.chat_history_service import ChatHistoryService
    from app.services.firebase_service import FirebaseService
except (ImportError, ModuleNotFoundError):
    from backend.app.services.vector_store import VectorStoreService
    from backend.app.services.llm_service import LLMService
    from backend.app.services.chat_history_service import ChatHistoryService
    from backend.app.services.firebase_service import FirebaseService

# Singleton service instances with resilient error handling
try:
    vector_store = VectorStoreService()
except Exception as _vse:
    print(f"[Deps] Notice initializing VectorStoreService: {_vse}")
    vector_store = None

try:
    llm_service = LLMService()
except Exception as _lse:
    print(f"[Deps] Notice initializing LLMService: {_lse}")
    llm_service = None

try:
    firebase_service = FirebaseService()
except Exception as _fse:
    print(f"[Deps] Notice initializing FirebaseService: {_fse}")
    firebase_service = None

try:
    chat_history = ChatHistoryService(firebase_service=firebase_service)
except Exception as _che:
    print(f"[Deps] Notice initializing ChatHistoryService: {_che}")
    chat_history = None
