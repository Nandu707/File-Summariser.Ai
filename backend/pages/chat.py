import asyncio
import re
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query
from .deps import vector_store, llm_service, chat_history, firebase_service
from .schemas import (
    AskRequest,
    AskResponse,
    CreateChatRequest,
    RenameChatRequest,
    SequentialQuestionsRequest
)

router = APIRouter(tags=["chat"])

# ==========================================
# CHAT SESSIONS ENDPOINTS
# ==========================================

@router.get("/api/chats")
async def get_all_chats(q: Optional[str] = Query(None, description="Search term for title and message text")):
    """
    Returns ALL chat sessions in one single list, sorted by updated_at (newest first).
    Supports search query parameter ?q=... filtering across title and message content.
    Syncs active files from ChromaDB registry into SQLite files table.
    """
    # Ensure active registry documents are registered in files table
    reg = vector_store._get_registry()
    for did, dinfo in reg.items():
        chat_history.register_file(did, dinfo.get("filename", "Document"), status="active")

    sessions = await asyncio.to_thread(chat_history.get_sessions, search_query=q)
    return sessions

@router.post("/api/chats")
async def create_chat_session(request: CreateChatRequest):
    """
    Creates a new chat session.
    User can choose scope ('all' or a specific active file_id).
    Allows multiple separate chats for the same file or for 'All files'.
    """
    reg = vector_store._get_registry()
    file_id = request.file_id
    file_name = request.file_name

    if request.scope == "file":
        if not file_id:
            raise HTTPException(status_code=400, detail="file_id is required when scope is 'file'")
        if chat_history.is_file_deleted(file_id):
            raise HTTPException(status_code=400, detail="Cannot create a new chat for a deleted file.")
        if not file_name:
            doc_info = reg.get(file_id, {})
            file_name = doc_info.get("filename", "Document")

    session = await asyncio.to_thread(
        chat_history.create_session,
        scope=request.scope or "all",
        file_id=file_id,
        file_name=file_name,
        title=request.title
    )
    return session

@router.get("/api/chats/{chat_id}")
async def get_chat_session(chat_id: str):
    """
    Returns session details along with its full list of messages.
    """
    if not chat_id.strip():
        raise HTTPException(status_code=400, detail="chat_id cannot be empty")

    session = await asyncio.to_thread(chat_history.get_session, chat_id)
    if not session:
        # If chat_id is 'all' or matches a document, create session on-the-fly
        reg = vector_store._get_registry()
        if chat_id == "all":
            session = await asyncio.to_thread(chat_history.create_session, scope="all", title="All files")
        elif chat_id in reg:
            fn = reg[chat_id].get("filename", "Document")
            session = await asyncio.to_thread(chat_history.create_session, scope="file", file_id=chat_id, file_name=fn, title=fn)
        else:
            raise HTTPException(status_code=404, detail="Chat session not found")

    messages = await asyncio.to_thread(chat_history.get_messages, session["id"])
    return {
        **session,
        "messages": messages
    }

@router.patch("/api/chats/{chat_id}")
@router.put("/api/chats/{chat_id}")
async def rename_chat_session(chat_id: str, request: RenameChatRequest):
    """
    Renames a chat session.
    """
    if not chat_id.strip():
        raise HTTPException(status_code=400, detail="chat_id cannot be empty")
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty")

    success = await asyncio.to_thread(chat_history.update_session_title, chat_id, request.title.strip())
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found or could not be renamed")

    return {"id": chat_id, "title": request.title.strip(), "status": "updated"}

@router.delete("/api/chats/{chat_id}")
@router.delete("/api/documents/{chat_id}/chat")
async def delete_chat_session(chat_id: str):
    """
    Permanently deletes only that chat session and all its conversation history.
    Triggered ONLY when user explicitly clicks 'Delete chat'.
    """
    if not chat_id.strip():
        raise HTTPException(status_code=400, detail="chat_id cannot be empty")

    if getattr(firebase_service, "is_active", False):
        try:
            await asyncio.to_thread(firebase_service.clear_chat_messages, chat_id)
        except Exception as fe:
            print(f"[chat_page] Notice clearing chat from Firebase: {fe}")

    await asyncio.to_thread(chat_history.delete_session, chat_id)
    return {
        "id": chat_id,
        "status": "deleted"
    }

# ==========================================
# QUESTION / ANSWER ENDPOINT
# ==========================================

@router.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Accepts question and chat_id (or doc_id).
    Enforces file deletion read-only rules:
      - If chat is scoped to a deleted file, rejects with 400.
      - Retrieves chunks ONLY from currently active files.
      - Safe context passing: never sends old messages that used deleted files to LLM.
      - Stores source details with file ID and file name.
      - Auto-titles session from the first question.
      - Touches session's updated_at timestamp so it moves to top of sidebar.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question cannot be empty."
        )

    # 1. Resolve session and scope
    session = None
    target_chat_id = request.chat_id
    raw_doc_id = (request.doc_id or "all").strip()

    if target_chat_id:
        session = await asyncio.to_thread(chat_history.get_session, target_chat_id)

    if not session:
        # Fall back to resolving by doc_id
        if raw_doc_id in ("all", "*", ""):
            # Find an existing 'all' session or create one
            all_sessions = await asyncio.to_thread(chat_history.get_sessions)
            all_s = next((s for s in all_sessions if s["scope"] == "all"), None)
            if all_s:
                session = all_s
            else:
                session = await asyncio.to_thread(chat_history.create_session, scope="all", title="All files")
        else:
            # File scoped
            reg = vector_store._get_registry()
            doc_info = reg.get(raw_doc_id, {})
            fn = doc_info.get("filename", "Document")
            session = await asyncio.to_thread(
                chat_history.create_session,
                scope="file",
                file_id=raw_doc_id,
                file_name=fn,
                title=f"Chat: {fn}"
            )

    effective_chat_id = session["id"]
    is_all = session["scope"] == "all"
    file_id = session.get("file_id")

    # 2. Check if the file is deleted - if so, chat is strictly read-only
    if not is_all and file_id:
        if chat_history.is_file_deleted(file_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This file was deleted. You can read the history but cannot ask new questions."
            )

    # 3. Get active files from registry and files table
    reg = vector_store._get_registry()
    active_file_ids = set(reg.keys())
    for fid in chat_history.get_active_file_ids():
        active_file_ids.add(fid)

    thread_filename = session.get("file_name") or ("All files" if is_all else "Document")

    try:
        # Store user question in SQLite
        await asyncio.to_thread(
            chat_history.add_message,
            chat_id=effective_chat_id,
            doc_id=file_id or "all",
            filename=thread_filename,
            role="user",
            content=request.question
        )

        # Retrieve top chunks from ChromaDB (strictly active files)
        chunks, metadatas, raw_sources = await asyncio.to_thread(
            vector_store.retrieve_top_chunks,
            doc_id=None if is_all else file_id,
            question=request.question,
            n_results=6 if is_all else 4
        )

        reg = vector_store._get_registry()
        if is_all:
            source_files = list(dict.fromkeys([m.get("filename") for m in metadatas if m.get("filename")]))
            doc_filename = ", ".join(source_files) if source_files else "all uploaded documents"
        else:
            doc_info = reg.get(file_id, {})
            doc_filename = doc_info.get("filename", thread_filename)
            source_files = [doc_filename] if doc_filename else []

        # Build detailed source citations (filename, file_id, page)
        source_details = []
        source_pages = []
        seen_details = set()
        for m in metadatas:
            p = int(m.get("page", 1))
            source_pages.append(p)
            fn = m.get("filename") or doc_filename
            d_id = m.get("doc_id") or (file_id if not is_all else "")
            dedup_key = (fn, d_id, p)
            if dedup_key not in seen_details:
                seen_details.add(dedup_key)
                source_details.append({
                    "file_id": d_id,
                    "doc_id": d_id,
                    "filename": fn,
                    "file_name": fn,
                    "page": p,
                    "is_deleted": False
                })
        sorted_sources = sorted(list(set(source_pages)))

        if not chunks:
            if is_all:
                if not reg or len(reg) == 0:
                    fallback_ans = "The information is not available. No documents found in the database. Please upload your files in the Documents tab first."
                else:
                    fallback_ans = "The information is not available in any of the currently active uploaded documents."
            elif file_id not in reg:
                fallback_ans = f"The information is not available. The document is not in the active database."
            else:
                fallback_ans = "The information is not available in this document. Please try rephrasing your question."

            fallback_seq = await asyncio.to_thread(
                vector_store.get_suggested_questions,
                file_id or "all",
                llm_service
            )

            await asyncio.to_thread(
                chat_history.add_message,
                chat_id=effective_chat_id,
                doc_id=file_id or "all",
                filename=thread_filename,
                role="assistant",
                content=fallback_ans,
                sources=[],
                source_details=[],
                suggested_questions=fallback_seq[:3] if fallback_seq else []
            )
            return {
                "answer": fallback_ans,
                "sources": [],
                "source_documents": [],
                "source_details": [],
                "suggested_questions": fallback_seq[:3] if fallback_seq else []
            }

        # 4. Safe history retrieval for LLM context:
        # Excludes any prior message that used a deleted file!
        safe_history = await asyncio.to_thread(
            chat_history.get_safe_history_for_llm,
            effective_chat_id,
            active_file_ids
        )

        # Generate answer using LLM
        answer = await asyncio.to_thread(
            llm_service.generate_answer,
            question=request.question,
            chunks=chunks,
            metadatas=metadatas,
            history=safe_history
        )

        # Generate sequential follow-up questions strictly relatable to this document and exchange
        try:
            seq_task = asyncio.to_thread(
                llm_service.generate_sequential_questions,
                filename=doc_filename,
                question=request.question,
                answer=answer,
                chunks=chunks
            )
            sequential_questions = await asyncio.wait_for(seq_task, timeout=2.5)
            if not sequential_questions:
                sequential_questions = llm_service._generate_heuristic_sequential_questions(
                    doc_filename, request.question, answer, chunks
                )[:3]
        except Exception:
            sequential_questions = llm_service._generate_heuristic_sequential_questions(
                doc_filename, request.question, answer, chunks
            )[:3]

        # Ground citations to retain chunks that genuinely contributed to the answer
        grounded_source_details = []
        grounded_source_pages = []
        grounded_source_files = set()
        seen_grounded = set()

        answer_lower = answer.lower()
        answer_words = set(re.findall(r"\b[a-z]{4,}\b", answer_lower))

        chunk_scores = []
        for idx, (chunk, m) in enumerate(zip(chunks, metadatas)):
            chunk_lower = chunk.lower()
            chunk_words = set(re.findall(r"\b[a-z]{4,}\b", chunk_lower))
            overlap = answer_words.intersection(chunk_words)

            phrase_matches = 0
            for s in re.split(r"[.\n•*-]", answer):
                s_words = re.sub(r"[^\w\s]", "", s.lower()).split()
                if len(s_words) >= 3:
                    for w_i in range(len(s_words) - 2):
                        trigram = " ".join(s_words[w_i:w_i + 3])
                        if trigram in chunk_lower:
                            phrase_matches += 1

            relevance_score = len(overlap) + (phrase_matches * 5)
            chunk_scores.append((relevance_score, idx, chunk, m))

        chunk_scores.sort(key=lambda x: x[0], reverse=True)
        max_relevance = chunk_scores[0][0] if chunk_scores else 0

        threshold = max(6, max_relevance * 0.3) if max_relevance > 0 else 0
        retained_metas = [
            m for score, idx, chunk, m in chunk_scores
            if score >= threshold or (max_relevance == 0 and idx == 0)
        ]

        if not retained_metas and metadatas:
            retained_metas = [metadatas[0]]

        for m in retained_metas:
            p = int(m.get("page", 1))
            fn = m.get("filename") or doc_filename
            d_id = m.get("doc_id") or (file_id if not is_all else "")
            dedup_key = (fn, d_id, p)
            if dedup_key not in seen_grounded:
                seen_grounded.add(dedup_key)
                grounded_source_pages.append(p)
                grounded_source_files.add(fn)
                grounded_source_details.append({
                    "file_id": d_id,
                    "doc_id": d_id,
                    "filename": fn,
                    "file_name": fn,
                    "page": p,
                    "is_deleted": False
                })

        sorted_sources = sorted(list(set(grounded_source_pages)))
        source_details = grounded_source_details
        source_files = list(grounded_source_files)

        # Store assistant response in persistent SQLite database
        await asyncio.to_thread(
            chat_history.add_message,
            chat_id=effective_chat_id,
            doc_id=file_id or "all",
            filename=thread_filename,
            role="assistant",
            content=answer,
            sources=sorted_sources,
            suggested_questions=sequential_questions,
            source_details=source_details
        )

        return {
            "answer": answer,
            "sources": sorted_sources,
            "source_documents": source_files,
            "source_details": source_details,
            "suggested_questions": sequential_questions
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[chat_page] Error querying documents in session {effective_chat_id}: {e}")
        await asyncio.to_thread(
            chat_history.add_message,
            chat_id=effective_chat_id,
            doc_id=file_id or "all",
            role="assistant",
            content=f"Error querying document: {str(e)}",
            is_error=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query document: {str(e)}"
        )

# ==========================================
# SEQUENTIAL QUESTIONS & LEGACY COMPATIBILITY
# ==========================================

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
    Returns persistent chat messages for doc_id or chat_id for backward compatibility.
    """
    if not doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    messages = await asyncio.to_thread(chat_history.get_messages, doc_id)
    return {
        "doc_id": doc_id,
        "messages": messages,
        "source": "sqlite"
    }
