import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from .deps import vector_store, llm_service, firebase_service
from .schemas import UploadResponse

router = APIRouter(tags=["upload"])

@router.post("/api/upload", response_model=UploadResponse)
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
        result = await asyncio.to_thread(vector_store.index_document, file.filename, content, llm_service, firebase_service)
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
