import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from .deps import vector_store, llm_service, firebase_service, chat_history
from .schemas import UploadResponse
from .auth import get_current_user, require_admin

router = APIRouter(tags=["upload"])

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB

@router.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_admin: dict = Depends(require_admin)
):
    """
    Accepts UploadFile (.pdf, .txt, .docx, .doc), extracts text with PyMuPDF / python-docx,
    splits extracted text using RecursiveCharacterTextSplitter (chunk_size=1000, chunk_overlap=200),
    generates embeddings, and stores in the single shared ChromaDB collection and file store.
    Strictly restricted to the administrator (returns 403 for non-admins).
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

        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds maximum allowed limit of 25MB."
            )

        # Uses PyMuPDF / python-docx + RecursiveCharacterTextSplitter + shared ChromaDB collection
        result = await asyncio.to_thread(
            vector_store.index_document,
            file.filename,
            content,
            llm_service,
            firebase_service
        )
        # Register new active file in persistent shared SQLite files table
        if result and result.get("doc_id"):
            chat_history.register_file(
                doc_id=result["doc_id"],
                filename=result.get("filename", file.filename),
                status="active"
            )
            # Auto-create initial chat session for the admin
            try:
                chat_history.create_session(
                    session_id=None,
                    doc_id=result["doc_id"],
                    title=result.get("filename", file.filename),
                    user_id=current_admin["id"]
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
