import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from .deps import vector_store, llm_service, firebase_service, chat_history
from .schemas import UploadResponse
from .auth import get_current_user

router = APIRouter(tags=["upload"])

@router.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Accepts UploadFile (.pdf, .txt, .docx, .doc), extracts text with PyMuPDF / python-docx,
    splits extracted text using RecursiveCharacterTextSplitter (chunk_size=1000, chunk_overlap=200),
    generates embeddings, and stores in isolated per-user collection and directory.
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

    user_id = current_user["id"]

    try:
        content = await file.read()
        if not content or len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty."
            )

        # Uses PyMuPDF / python-docx + RecursiveCharacterTextSplitter + ChromaDB isolated collection
        result = await asyncio.to_thread(
            vector_store.index_document,
            file.filename,
            content,
            llm_service,
            firebase_service,
            user_id
        )
        # Register new active file in persistent SQLite files table scoped to user_id
        if result and result.get("doc_id"):
            chat_history.register_file(
                doc_id=result["doc_id"],
                filename=result.get("filename", file.filename),
                status="active",
                user_id=user_id
            )
            # Auto-create initial chat session for this file
            try:
                chat_history.create_session(
                    session_id=None,
                    doc_id=result["doc_id"],
                    title=result.get("filename", file.filename),
                    user_id=user_id
                )
            except Exception as se:
                print(f"[Upload] Notice auto-creating session: {se}")

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
