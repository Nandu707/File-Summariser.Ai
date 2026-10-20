import asyncio
from fastapi import APIRouter, HTTPException, status
from .deps import vector_store, llm_service, chat_history, firebase_service
from .schemas import AskRequest, AskResponse, SequentialQuestionsRequest

router = APIRouter(tags=["chat"])

@router.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Accepts { "doc_id": str, "question": str },
    persists user question to SQLite DB & Firebase Firestore,
    retrieves the top 4 chunks from ChromaDB via Hybrid RRF Search,
    passes them to the LLM with a strict context-only prompt,
    persists assistant response to SQLite DB & Firebase Firestore,
    and returns: { "answer": str, "sources": list[int], "suggested_questions": list[str] }
    """
    raw_doc_id = (request.doc_id or "all").strip()
    is_all = raw_doc_id.lower() in ("all", "*", "")
    effective_doc_id = "all" if is_all else raw_doc_id

    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question cannot be empty."
        )

    try:
        # Store user question in persistent SQLite database & Firebase
        # Store user question in persistent SQLite database (instant local response)
        await asyncio.to_thread(
            chat_history.add_message,
            doc_id=effective_doc_id,
            role="user",
            content=request.question
        )
        # Non-blocking Firebase save
        if getattr(firebase_service, "is_active", False):
            asyncio.create_task(
                asyncio.to_thread(
                    firebase_service.save_chat_message,
                    doc_id=effective_doc_id,
                    role="user",
                    content=request.question
                )
            )

        # Retrieve top 4 chunks from ChromaDB asynchronously
        chunks, metadatas, raw_sources = await asyncio.to_thread(
            vector_store.retrieve_top_chunks,
            doc_id=effective_doc_id,
            question=request.question,
            n_results=4
        )

        reg = vector_store._get_registry()
        if is_all:
            source_files = list(dict.fromkeys([m.get("filename") for m in metadatas if m.get("filename")]))
            doc_filename = ", ".join(source_files) if source_files else "all uploaded documents"
        else:
            doc_info = reg.get(effective_doc_id, {})
            doc_filename = doc_info.get("filename", "document")
            source_files = [doc_filename] if doc_filename else []

        # Build detailed source citations (filename, doc_id, page)
        source_details = []
        source_pages = []
        seen_details = set()
        for m in metadatas:
            p = int(m.get("page", 1))
            source_pages.append(p)
            fn = m.get("filename") or doc_filename
            d_id = m.get("doc_id") or effective_doc_id
            dedup_key = (fn, d_id, p)
            if dedup_key not in seen_details:
                seen_details.add(dedup_key)
                source_details.append({
                    "filename": fn,
                    "doc_id": d_id,
                    "page": p
                })
        sorted_sources = sorted(list(set(source_pages)))

        if not chunks:
            if is_all:
                if not reg or len(reg) == 0:
                    fallback_ans = "No documents found in the database. Please upload your files in the Documents tab first."
                else:
                    fallback_ans = "No relevant content could be retrieved from the uploaded documents for your question. Please try rephrasing your question."
            elif effective_doc_id not in reg:
                fallback_ans = f"Document not found. The document ID '{effective_doc_id}' does not exist in the database. Please try re-uploading the document."
            else:
                fallback_ans = "No relevant content could be retrieved from this document. Please try rephrasing your question or re-uploading the document."

            fallback_seq = await asyncio.to_thread(
                vector_store.get_suggested_questions,
                effective_doc_id,
                llm_service
            )

            await asyncio.to_thread(
                chat_history.add_message,
                doc_id=effective_doc_id,
                role="assistant",
                content=fallback_ans,
                sources=[],
                suggested_questions=fallback_seq[:3] if fallback_seq else []
            )
            return {
                "answer": fallback_ans,
                "sources": [],
                "source_documents": [],
                "source_details": [],
                "suggested_questions": fallback_seq[:3] if fallback_seq else []
            }

        # Concurrently generate answer and sequential questions using ultra-fast LLM
        answer_task = asyncio.to_thread(
            llm_service.generate_answer,
            question=request.question,
            chunks=chunks,
            metadatas=metadatas
        )
        seq_task = asyncio.to_thread(
            llm_service.generate_sequential_questions,
            filename=doc_filename,
            question=request.question,
            answer="",
            chunks=chunks
        )
        answer, sequential_questions = await asyncio.gather(answer_task, seq_task)

        # Store assistant response in persistent SQLite database & background Firebase
        await asyncio.to_thread(
            chat_history.add_message,
            doc_id=effective_doc_id,
            role="assistant",
            content=answer,
            sources=sorted_sources,
            suggested_questions=sequential_questions
        )
        if getattr(firebase_service, "is_active", False):
            asyncio.create_task(
                asyncio.to_thread(
                    firebase_service.save_chat_message,
                    doc_id=effective_doc_id,
                    role="assistant",
                    content=answer,
                    sources=sorted_sources,
                    suggested_questions=sequential_questions
                )
            )

        return {
            "answer": answer,
            "sources": sorted_sources,
            "source_documents": source_files,
            "source_details": source_details,
            "suggested_questions": sequential_questions
        }

    except Exception as e:
        print(f"[chat_page] Error querying document {effective_doc_id}: {e}")
        await asyncio.to_thread(
            chat_history.add_message,
            doc_id=request.doc_id,
            role="assistant",
            content=f"Error querying document: {str(e)}",
            is_error=True
        )
        if getattr(firebase_service, "is_active", False):
            try:
                await asyncio.to_thread(
                    firebase_service.save_chat_message,
                    doc_id=request.doc_id,
                    role="assistant",
                    content=f"Error querying document: {str(e)}",
                    is_error=True
                )
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query document: {str(e)}"
        )

@router.post("/api/documents/{doc_id}/sequential-questions")
@router.post("/api/sequential-questions")
async def get_sequential_questions_endpoint(request: SequentialQuestionsRequest):
    """
    Suggests 3 sequential follow-up questions using LLM based on the document and the previous question/answer.
    """
    if not request.doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question cannot be empty")

    reg = vector_store._get_registry()
    doc_info = reg.get(request.doc_id, {})
    doc_filename = doc_info.get("filename", "document")

    chunks, _, _ = await asyncio.to_thread(
        vector_store.retrieve_top_chunks,
        doc_id=request.doc_id,
        question=request.question,
        n_results=4
    )

    questions = await asyncio.to_thread(
        llm_service.generate_sequential_questions,
        filename=doc_filename,
        question=request.question,
        answer=request.answer or "",
        chunks=chunks
    )
    return {
        "doc_id": request.doc_id,
        "sequential_questions": questions,
        "suggested_questions": questions
    }

@router.get("/api/documents/{doc_id}/chat")
async def get_document_chat(doc_id: str):
    """
    Returns the persistent chat history for the specified document from Firebase Firestore (or SQLite fallback).
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    messages = await asyncio.to_thread(chat_history.get_messages, doc_id)
    if messages and len(messages) > 0:
        return {
            "doc_id": doc_id,
            "messages": messages,
            "source": "sqlite"
        }

    if getattr(firebase_service, "is_active", False):
        try:
            fb_messages = await asyncio.to_thread(firebase_service.get_chat_messages, doc_id)
            if fb_messages and len(fb_messages) > 0:
                return {
                    "doc_id": doc_id,
                    "messages": fb_messages,
                    "source": "firebase"
                }
        except Exception:
            pass

    return {
        "doc_id": doc_id,
        "messages": [],
        "source": "sqlite"
    }

@router.delete("/api/documents/{doc_id}/chat")
async def clear_document_chat(doc_id: str):
    """
    Clears the chat history for the specified document from Firebase Firestore and SQLite.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    if getattr(firebase_service, "is_active", False):
        try:
            await asyncio.to_thread(firebase_service.clear_chat_messages, doc_id)
        except Exception as fe:
            print(f"[chat_page] Notice clearing chat from Firebase: {fe}")

    await asyncio.to_thread(chat_history.clear_messages, doc_id)
    return {
        "doc_id": doc_id,
        "status": "cleared"
    }
