import asyncio
from typing import Optional
import urllib.parse
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, status
from fastapi.responses import FileResponse
from .deps import vector_store, llm_service, chat_history, firebase_service
from .auth import get_current_user, require_admin

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.get("")
@router.get("/")
def get_documents(current_user: dict = Depends(get_current_user)):
    """
    Returns list of all active shared documents uploaded by the administrator.
    All approved users have read-only visibility into admin documents.
    """
    docs = vector_store.list_documents()
    for d in docs:
        chat_history.register_file(d["doc_id"], d.get("filename", "Document"), "active")
    return docs

@router.delete("/{doc_id}")
def delete_document(doc_id: str, current_admin: dict = Depends(require_admin)):
    """
    Deletes an indexed document. Strictly restricted to the administrator.
    Removes chunks and embeddings from the shared ChromaDB index, while preserving
    existing chat sessions as read-only with 'File deleted' status.
    """
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

    # Clean Firebase Firestore document record and storage if active
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

@router.post("/{doc_id}/replace")
async def replace_document(
    doc_id: str,
    file: UploadFile = File(...),
    current_admin: dict = Depends(require_admin)
):
    """
    Replaces an existing document with a new version.
    Strictly restricted to the administrator (403 for non-admins).
    Purges old chunks from the index so no stale content remains, then indexes the replacement file.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No replacement file provided.")

    ext = file.filename.lower().split(".")[-1]
    if ext not in ["pdf", "txt", "md", "docx", "doc"]:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded replacement file is empty.")

    # 1. Purge old document from index and file store completely (no stale content left)
    vector_store.delete_document(doc_id)

    # 2. Index new replacement document into shared index
    result = await asyncio.to_thread(
        vector_store.index_document,
        file.filename,
        content,
        llm_service,
        firebase_service
    )

    if result and result.get("doc_id"):
        chat_history.register_file(
            doc_id=result["doc_id"],
            filename=result.get("filename", file.filename),
            status="active"
        )

    return {
        "message": "Document successfully replaced and re-indexed with no stale content",
        "old_doc_id": doc_id,
        "new_document": result
    }

@router.get("/{doc_id}/pages/{page_num}")
async def get_document_page(
    doc_id: str,
    page_num: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns specific page content, total page count, document filename, and file viewing URLs.
    Protected by user isolation.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")
    if page_num < 1:
        raise HTTPException(status_code=400, detail="page_num must be >= 1")

    user_id = current_user["id"]
    page_data = await asyncio.to_thread(vector_store.get_document_page, doc_id, page_num, user_id)
    if not page_data or not page_data.get("filename") or page_data.get("filename") == "Access Denied":
        raise HTTPException(status_code=404, detail="Document or page not found or access denied")
    return page_data

@router.get("/{doc_id}/file")
@router.get("/{doc_id}/file/{filename}")
@router.get("/{doc_id}/view")
@router.get("/{doc_id}/view/{filename}")
async def get_document_file(
    doc_id: str,
    filename: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Serves the document file inline for authenticated owner so PDF browsers can jump to pages.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    user_id = current_user["id"]
    file_path = await asyncio.to_thread(vector_store.get_document_file_path, doc_id, user_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on server or access denied")

    reg = vector_store._get_registry()
    doc_info = reg.get(doc_id, {})
    doc_filename = doc_info.get("filename", file_path.name)
    ext = doc_filename.lower().split(".")[-1]

    media_type_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain; charset=utf-8",
        "md": "text/markdown; charset=utf-8",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")

    ascii_clean = doc_filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_clean:
        ascii_clean = f"document.{ext}"
    encoded_fn = urllib.parse.quote(doc_filename)

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{ascii_clean}"; filename*=UTF-8\'\'{encoded_fn}'}
    )

@router.get("/{doc_id}/suggested-questions")
async def get_suggested_questions(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns suggested questions specifically tailored to the selected document for the current user.
    """
    clean_id = doc_id.strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    user_id = current_user["id"]
    target_id = clean_id
    if clean_id.startswith("chat_"):
        session = await asyncio.to_thread(chat_history.get_session, clean_id, user_id)
        if session:
            if session.get("scope") == "file" and session.get("file_id"):
                target_id = session["file_id"]
            elif session.get("scope") == "all":
                target_id = "all"
        else:
            raise HTTPException(status_code=404, detail="Chat session not found or access denied")

    questions = await asyncio.to_thread(vector_store.get_suggested_questions, target_id, llm_service, user_id)
    return {
        "doc_id": doc_id,
        "suggested_questions": questions
    }
