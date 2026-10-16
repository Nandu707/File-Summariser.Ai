import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Ensure local backend path has highest priority in sys.path
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
for p in [str(ROOT_DIR), str(BASE_DIR)]:
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BASE_DIR))

from app.services.vector_store import VectorStoreService
from app.services.llm_service import LLMService
from app.services.chat_history_service import ChatHistoryService

load_dotenv()

app = FastAPI(
    title="File Summariser.Ai API",
    description="Full-stack Document Question-Answering and Summarization system powered by FastAPI, PyMuPDF, ChromaDB, and React.",
    version="1.0.0"
)

# CORS Configuration
# "Always enable CORS in FastAPI for http://localhost:5173"
cors_origins_env = os.getenv("CORS_ORIGIN", "http://localhost:5173")
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if cors_origins_env not in origins:
    origins.append(cors_origins_env)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
vector_store = VectorStoreService()
llm_service = LLMService()
chat_history = ChatHistoryService()

# Startup logging for debugging
print(f"[startup] Vector DB path: {vector_store.persist_dir}")
print(f"[startup] Collection: {vector_store.collection.name} ({vector_store.collection.count()} chunks)")
print(f"[startup] Documents in registry: {len(vector_store.list_documents())}")
print(f"[startup] Gemini API key configured: {bool(llm_service.gemini_api_key)}")

import asyncio

# Pydantic Schemas
class AskRequest(BaseModel):
    doc_id: str = Field(..., description="The unique ID of the indexed document")
    question: str = Field(..., description="The user's question regarding the document")

class AskResponse(BaseModel):
    answer: str
    sources: List[int]

class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    chunks: int
    suggested_questions: Optional[List[str]] = None

@app.get("/")
def root():
    return {
        "message": "File Summariser.Ai Backend is running.",
        "docs_url": "/docs",
        "health": "/api/health"
    }

@app.get("/api/health")
def health():
    docs = vector_store.list_documents()
    return {
        "status": "healthy",
        "documents_count": len(docs),
        "vector_db_path": str(vector_store.persist_dir),
        "cors_allowed": origins,
        "llm_gemini_active": bool(os.getenv("GEMINI_API_KEY")),
        "llm_openai_active": bool(os.getenv("OPENAI_API_KEY"))
    }

@app.get("/api/documents")
def get_documents():
    """Returns list of indexed documents in persistent ChromaDB storage."""
    return vector_store.list_documents()

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    """Deletes an indexed document from ChromaDB, registry, and clears its chat history."""
    success = vector_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or could not be deleted")
    chat_history.clear_messages(doc_id)
    return {"message": "Document deleted successfully", "doc_id": doc_id}

@app.get("/api/documents/{doc_id}/suggested-questions")
async def get_suggested_questions(doc_id: str):
    """
    Returns 3 to 4 variable questions specifically tailored to the selected document.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")
    questions = await asyncio.to_thread(vector_store.get_suggested_questions, doc_id, llm_service)
    return {
        "doc_id": doc_id,
        "suggested_questions": questions
    }

@app.get("/api/documents/{doc_id}/chat")
async def get_document_chat(doc_id: str):
    """
    Returns the persistent chat history for the specified document from SQLite.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")
    messages = await asyncio.to_thread(chat_history.get_messages, doc_id)
    return {
        "doc_id": doc_id,
        "messages": messages
    }

@app.delete("/api/documents/{doc_id}/chat")
async def clear_document_chat(doc_id: str):
    """
    Clears the chat history for the specified document from SQLite.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")
    await asyncio.to_thread(chat_history.clear_messages, doc_id)
    return {
        "doc_id": doc_id,
        "status": "cleared"
    }

@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Accepts UploadFile (.pdf, .txt, .docx, .doc), extracts text with PyMuPDF / python-docx,
    splits extracted text using RecursiveCharacterTextSplitter (chunk_size=1000, chunk_overlap=200),
    generates embeddings, and stores in persistent ChromaDB client at ./vector_db with doc_id and page metadata.
    Returns: { "doc_id": str, "filename": str, "chunks": int, "suggested_questions": list[str] }
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided in upload."
        )

    ext = file.filename.lower().split(".")[-1]
    if ext not in ["pdf", "txt", "md", "docx", "doc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Supported formats are .pdf, .txt, .docx, and .doc."
        )

    try:
        content = await file.read()
        if not content or len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty."
            )

        # Uses PyMuPDF / python-docx + RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200) + ChromaDB
        # Non-blocking async thread execution for fast responsiveness on large files
        result = await asyncio.to_thread(vector_store.index_document, file.filename, content, llm_service)
        return result

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while parsing and indexing document: {str(e)}"
        )

@app.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Accepts { "doc_id": str, "question": str },
    persists user question to SQLite DB,
    retrieves the top 4 chunks from ChromaDB via Hybrid RRF Search,
    passes them to the LLM with a strict context-only prompt,
    persists assistant response to SQLite DB,
    and returns: { "answer": str, "sources": list[int] }
    """
    if not request.doc_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="doc_id cannot be empty."
        )

    if not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question cannot be empty."
        )

    try:
        # Store user question in persistent SQLite database
        await asyncio.to_thread(
            chat_history.add_message,
            doc_id=request.doc_id,
            role="user",
            content=request.question
        )

        # Retrieve top 4 chunks from ChromaDB asynchronously
        chunks, metadatas, sources = await asyncio.to_thread(
            vector_store.retrieve_top_chunks,
            doc_id=request.doc_id,
            question=request.question,
            n_results=4
        )

        if not chunks:
            # Check if the document exists at all in the registry
            reg = vector_store._get_registry()
            if request.doc_id not in reg:
                fallback_ans = f"Document not found. The document ID '{request.doc_id}' does not exist in the database. Please try re-uploading the document."
            else:
                fallback_ans = "No relevant content could be retrieved from this document. Please try rephrasing your question or re-uploading the document."

            await asyncio.to_thread(
                chat_history.add_message,
                doc_id=request.doc_id,
                role="assistant",
                content=fallback_ans,
                sources=[]
            )
            return {
                "answer": fallback_ans,
                "sources": []
            }

        # Pass to LLM with strict context-only prompt
        answer = await asyncio.to_thread(
            llm_service.generate_answer,
            question=request.question,
            chunks=chunks,
            metadatas=metadatas
        )

        # Extract cited pages if explicitly referenced in answer, else use retrieved sources
        import re
        cited_pages = [int(p) for p in re.findall(r"(?:Page|p\.)\s*(\d+)", answer, re.IGNORECASE)]
        valid_cited = [p for p in cited_pages if p in sources] if sources else cited_pages
        final_sources = sorted(list(set(valid_cited if valid_cited else sources)))

        # Store assistant response and cited sources in persistent SQLite database
        await asyncio.to_thread(
            chat_history.add_message,
            doc_id=request.doc_id,
            role="assistant",
            content=answer,
            sources=final_sources
        )

        # Return answer along with source page numbers
        return {
            "answer": answer,
            "sources": final_sources
        }

    except Exception as e:
        print(f"[ask] Error querying document {request.doc_id}: {e}")
        # Record error message in chat history so context is preserved
        await asyncio.to_thread(
            chat_history.add_message,
            doc_id=request.doc_id,
            role="assistant",
            content=f"Error querying document: {str(e)}",
            is_error=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query document: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
