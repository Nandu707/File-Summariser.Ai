import os
from fastapi import APIRouter
from .deps import vector_store, firebase_service

router = APIRouter(tags=["health"])

@router.get("/")
def root():
    return {
        "message": "File Summariser.Ai Backend is running.",
        "docs_url": "/docs",
        "health": "/api/health"
    }

@router.get("/api/health")
def health():
    docs = vector_store.list_documents()
    cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cors_origins_env = os.getenv("CORS_ORIGIN")
    if cors_origins_env and cors_origins_env not in cors_origins:
        cors_origins.append(cors_origins_env)

    return {
        "status": "healthy",
        "documents_count": len(docs),
        "vector_db_path": str(vector_store.persist_dir),
        "cors_allowed": cors_origins,
        "llm_gemini_active": bool(os.getenv("GEMINI_API_KEY")),
        "llm_openai_active": bool(os.getenv("OPENAI_API_KEY")),
        "firebase_active": getattr(firebase_service, "is_active", False)
    }
