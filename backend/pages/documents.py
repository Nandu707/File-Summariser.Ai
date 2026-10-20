import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .deps import vector_store, llm_service, chat_history, firebase_service

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.get("")
@router.get("/")
def get_documents():
    """Returns list of indexed documents in persistent ChromaDB storage and Firebase."""
    return vector_store.list_documents()

@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    """Deletes an indexed document from ChromaDB, registry, Firebase, and clears its chat history."""
    success = vector_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or could not be deleted")
    chat_history.clear_messages(doc_id)
    if getattr(firebase_service, "is_active", False):
        try:
            firebase_service.delete_document(doc_id)
        except Exception as fe:
            print(f"[documents_page] Notice deleting from Firebase: {fe}")
    return {"message": "Document deleted successfully", "doc_id": doc_id}

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

@router.get("/{doc_id}/file")
async def get_document_file(doc_id: str):
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

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )

@router.get("/{doc_id}/suggested-questions")
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
