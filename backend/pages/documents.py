import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .deps import vector_store, llm_service, chat_history, firebase_service

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.get("")
@router.get("/")
def get_documents():
    """Returns list of indexed documents in persistent ChromaDB storage and Firebase."""
    docs = vector_store.list_documents()
    for d in docs:
        chat_history.register_file(d["doc_id"], d.get("filename", "Document"), "active")
    return docs

@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    """Deletes an indexed document from ChromaDB and registry while preserving chats as read-only."""
    # Look up registry metadata before deletion to resolve IDs and filenames
    reg = vector_store._get_registry()
    target_id = doc_id
    target_doc = reg.get(doc_id)
    if not target_doc:
        for did, info in reg.items():
            if info.get("filename") == doc_id or did == doc_id:
                target_id = did
                target_doc = info
                break

    filename = target_doc.get("filename") if target_doc else None

    # Perform vector store, file system, and registry deletion
    success = vector_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or could not be deleted")

    # Mark file status as deleted in chat history so chats remain viewable and read-only
    chat_history.mark_file_deleted(target_id)
    if doc_id != target_id:
        chat_history.mark_file_deleted(doc_id)

    # Clean Firebase Firestore document record and storage if active, but leave chat if desired
    if getattr(firebase_service, "is_active", False):
        try:
            firebase_service.delete_document(target_id)
            if doc_id != target_id:
                firebase_service.delete_document(doc_id)
        except Exception as fe:
            print(f"[documents_page] Notice deleting from Firebase: {fe}")

    return {
        "message": "Document removed from index and registry; chat preserved as read-only",
        "doc_id": target_id,
        "filename": filename
    }

@router.get("/{doc_id}/pages/{page_num}")
async def get_document_page(doc_id: str, page_num: int):
    """
    Returns specific page content, total page count, document filename, and file viewing URLs.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")
    if page_num < 1:
        raise HTTPException(status_code=400, detail="page_num must be >= 1")

    page_data = await asyncio.to_thread(vector_store.get_document_page, doc_id, page_num)
    if not page_data or not page_data.get("filename"):
        raise HTTPException(status_code=404, detail="Document or page not found")
    return page_data

from typing import Optional

@router.get("/{doc_id}/file")
@router.get("/{doc_id}/file/{filename}")
@router.get("/{doc_id}/view")
@router.get("/{doc_id}/view/{filename}")
async def get_document_file(doc_id: str, filename: Optional[str] = None):
    """
    Serves the document file inline so PDF browsers can jump directly to #page={page_num}.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    file_path = await asyncio.to_thread(vector_store.get_document_file_path, doc_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on server")

    reg = vector_store._get_registry()
    doc_info = reg.get(doc_id, {})
    filename = doc_info.get("filename", file_path.name)
    ext = filename.lower().split(".")[-1]

    media_type_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")

    import urllib.parse
    ascii_clean = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_clean:
        ascii_clean = f"document.{ext}"
    encoded_fn = urllib.parse.quote(filename)

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{ascii_clean}"; filename*=UTF-8\'\'{encoded_fn}'}
    )

@router.get("/{doc_id}/suggested-questions")
async def get_suggested_questions(doc_id: str):
    """
    Returns 3 to 4 variable questions specifically tailored to the selected document.
    """
    clean_id = doc_id.strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    target_id = clean_id
    if clean_id.startswith("chat_"):
        session = await asyncio.to_thread(chat_history.get_session, clean_id)
        if session:
            if session.get("scope") == "file" and session.get("file_id"):
                target_id = session["file_id"]
            elif session.get("scope") == "all":
                target_id = "all"

    questions = await asyncio.to_thread(vector_store.get_suggested_questions, target_id, llm_service)
    return {
        "doc_id": doc_id,
        "suggested_questions": questions
    }
