import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Reconfigure stdout/stderr on Windows to UTF-8 with character replacement
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure local backend path and app services are in sys.path
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
for p in [str(BASE_DIR), str(ROOT_DIR), str(BASE_DIR / "app"), str(ROOT_DIR / "app")]:
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv()

# Import page routers and services from the pages directory
from pages import (
    documents_router,
    chat_router,
    upload_router,
    health_router,
    auth_router,
    vector_store,
    llm_service,
    chat_history,
    firebase_service,
    AskRequest,
    AskResponse,
    SequentialQuestionsRequest,
    UploadResponse
)
from pages.chat import ask_question
from pages.upload import upload_document

app = FastAPI(
    title="File Summariser.Ai API",
    description="Full-stack Document Question-Answering and Summarization system powered by FastAPI, PyMuPDF, ChromaDB, and React.",
    version="1.0.0"
)

# Background scheduler for daily automatic chat cleanup
if not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(daemon=True)
        def run_scheduled_cleanup():
            try:
                retention_days = int(os.getenv("CHAT_RETENTION_DAYS", "30"))
                if chat_history and hasattr(chat_history, "cleanup_old_chats"):
                    purged = chat_history.cleanup_old_chats(retention_days=retention_days)
                    print(f"[Scheduler] Scheduled chat cleanup: purged {purged} old sessions (retention: {retention_days} days).")
            except Exception as se:
                print(f"[Scheduler] Notice during chat cleanup: {se}")

        scheduler.add_job(run_scheduled_cleanup, 'interval', hours=24)
        scheduler.start()
        run_scheduled_cleanup()
    except Exception as sched_err:
        print(f"[Scheduler] Notice initializing APScheduler: {sched_err}")

# CORS Configuration
cors_origins_env = os.getenv("CORS_ORIGIN", "http://localhost:5173")
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if cors_origins_env and cors_origins_env not in origins:
    origins.append(cors_origins_env)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup logging for debugging (wrapped safely)
try:
    if vector_store:
        print(f"[startup] Vector DB path: {vector_store.persist_dir}")
        print(f"[startup] Collection: {vector_store.collection.name} ({vector_store.collection.count()} chunks)")
        print(f"[startup] Documents in registry: {len(vector_store.list_documents())}")
    if llm_service:
        print(f"[startup] Gemini API key configured: {bool(llm_service.gemini_api_key)}")
except Exception as e:
    print(f"[startup] Notice during startup logging: {e}")

# ROUTE ALL PAGES AND COMPONENTS FROM MAIN.PY
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(upload_router)
app.include_router(documents_router)
app.include_router(chat_router)

# Mount frontend build static files & route frontend pages if dist directory is present
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static_assets")

    @app.get("/app/{full_path:path}")
    @app.get("/chat")
    @app.get("/documents")
    @app.get("/upload")
    @app.get("/system")
    async def serve_frontend_spa(full_path: str = ""):
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Frontend build index.html not found"}

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
