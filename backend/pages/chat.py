import asyncio
import re
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query, Depends
from .deps import vector_store, llm_service, chat_history, firebase_service
from .schemas import (
    AskRequest,
    AskResponse,
    CreateChatRequest,
    RenameChatRequest,
    SequentialQuestionsRequest
)
from .auth import get_current_user

router = APIRouter(tags=["chat"])

# ==========================================
# CHAT SESSIONS ENDPOINTS
# ==========================================

@router.get("/api/chats")
async def get_all_chats(
    q: Optional[str] = Query(None, description="Search term for title and message text"),
    current_user: dict = Depends(get_current_user)
):
    """
    Returns ALL chat sessions for the current user, sorted by updated_at (newest first).
    Supports search query parameter ?q=... filtering across title and message content.
    """
    user_id = current_user["id"]
    # Ensure active registry documents for this user are registered in files table
    reg = vector_store._get_registry()
    for did, dinfo in reg.items():
        if not dinfo.get("user_id") or str(dinfo.get("user_id")) == str(user_id):
            chat_history.register_file(did, dinfo.get("filename", "Document"), status="active", user_id=user_id)

    sessions = await asyncio.to_thread(chat_history.get_sessions, search_query=q, user_id=user_id)
    return sessions

@router.post("/api/chats")
async def create_chat_session(
    request: CreateChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Creates a new chat session for the current user.
    User can choose scope ('all' or a specific active file_id).
    Allows multiple separate chats for the same file or for 'All files'.
    """
    user_id = current_user["id"]
    reg = vector_store._get_registry()
    file_id = request.file_id
    file_name = request.file_name

    if request.scope == "file":
        if not file_id:
            raise HTTPException(status_code=400, detail="file_id is required when scope is 'file'")
        
        # Verify file ownership
        if file_id in reg:
            doc_owner = reg[file_id].get("user_id")
            if doc_owner and str(doc_owner) != str(user_id):
                raise HTTPException(status_code=403, detail="Forbidden: You do not own this document.")
        
        file_rec = chat_history.get_file(file_id, user_id=user_id)
        if file_rec and file_rec.get("status") == "deleted":
            raise HTTPException(status_code=400, detail="Cannot create a new chat for a deleted file.")

        if not file_name:
            doc_info = reg.get(file_id, {})
            file_name = doc_info.get("filename", "Document")

    session = await asyncio.to_thread(
        chat_history.create_session,
        scope=request.scope or "all",
        file_id=file_id,
        file_name=file_name,
        title=request.title,
        user_id=user_id
    )
    return session

@router.get("/api/chats/{chat_id}")
async def get_chat_session(
    chat_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns session details along with its full list of messages.
    Strictly isolated by user_id.
    """
    if not chat_id.strip():
        raise HTTPException(status_code=400, detail="chat_id cannot be empty")

    user_id = current_user["id"]
    session = await asyncio.to_thread(chat_history.get_session, chat_id, user_id)
    if not session:
        # If chat_id is 'all' or matches a document owned by user, create session on-the-fly
        reg = vector_store._get_registry()
        if chat_id == "all":
            session = await asyncio.to_thread(chat_history.create_session, scope="all", title="All files", user_id=user_id)
        elif chat_id in reg and (not reg[chat_id].get("user_id") or str(reg[chat_id].get("user_id")) == str(user_id)):
            fn = reg[chat_id].get("filename", "Document")
            session = await asyncio.to_thread(chat_history.create_session, scope="file", file_id=chat_id, file_name=fn, title=fn, user_id=user_id)
        else:
            raise HTTPException(status_code=404, detail="Chat session not found or access denied")

    messages = await asyncio.to_thread(chat_history.get_messages, session["id"], user_id)
    return {
        **session,
        "messages": messages
    }

@router.patch("/api/chats/{chat_id}")
@router.put("/api/chats/{chat_id}")
async def rename_chat_session(
    chat_id: str,
    request: RenameChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Renames a chat session owned by current user.
    """
    if not chat_id.strip():
        raise HTTPException(status_code=400, detail="chat_id cannot be empty")
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty")

    user_id = current_user["id"]
    success = await asyncio.to_thread(chat_history.update_session_title, chat_id, request.title.strip(), user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found or could not be renamed")

    return {"id": chat_id, "title": request.title.strip(), "status": "updated"}

@router.delete("/api/chats/{chat_id}")
@router.delete("/api/documents/{chat_id}/chat")
async def delete_chat_session(
    chat_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Permanently deletes only that chat session and all its conversation history.
    Strictly checks ownership.
    """
    if not chat_id.strip():
        raise HTTPException(status_code=400, detail="chat_id cannot be empty")

    user_id = current_user["id"]
    if getattr(firebase_service, "is_active", False):
        try:
            await asyncio.to_thread(firebase_service.clear_chat_messages, chat_id)
        except Exception as fe:
            print(f"[chat_page] Notice clearing chat from Firebase: {fe}")

    success = await asyncio.to_thread(chat_history.delete_session, chat_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found or could not be deleted")

    return {
        "id": chat_id,
        "status": "deleted"
    }

# ==========================================
# QUESTION / ANSWER ENDPOINT
# ==========================================

@router.post("/api/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Accepts question and chat_id (or doc_id) for current user.
    Enforces per-user isolation:
      - Searches only the user's ChromaDB collection.
      - Safe context passing: never leaks or includes data from other users.
      - Enforces file deletion read-only rules.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question cannot be empty."
        )

    user_id = current_user["id"]

    # 1. Resolve session and scope
    session = None
    target_chat_id = request.chat_id
    raw_doc_id = (request.doc_id or "all").strip()

    if target_chat_id:
        session = await asyncio.to_thread(chat_history.get_session, target_chat_id, user_id)

    if not session:
        # Fall back to resolving by doc_id
        if raw_doc_id in ("all", "*", ""):
            # Find an existing 'all' session or create one for this user
            all_sessions = await asyncio.to_thread(chat_history.get_sessions, None, user_id)
            all_s = next((s for s in all_sessions if s["scope"] == "all"), None)
            if all_s:
                session = all_s
            else:
                session = await asyncio.to_thread(chat_history.create_session, scope="all", title="All files", user_id=user_id)
        else:
            # File scoped - verify user ownership
            reg = vector_store._get_registry()
            doc_info = reg.get(raw_doc_id, {})
            owner = doc_info.get("user_id")
            if owner and str(owner) != str(user_id):
                raise HTTPException(status_code=403, detail="Forbidden: You do not own this document.")
            
            fn = doc_info.get("filename", "Document")
            session = await asyncio.to_thread(
                chat_history.create_session,
                scope="file",
                file_id=raw_doc_id,
                file_name=fn,
                title=f"Chat: {fn}",
                user_id=user_id
            )

    effective_chat_id = session["id"]
    is_all = session["scope"] == "all"
    file_id = session.get("file_id")

    # 2. Check if the file is deleted - if so, chat is strictly read-only
    if not is_all and file_id:
        if chat_history.is_file_deleted(file_id, user_id=user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This file was deleted. You can read the history but cannot ask new questions."
            )

    # 3. Get active files from registry and files table for this user
    reg = vector_store._get_registry()
    user_reg = {k: v for k, v in reg.items() if not v.get("user_id") or str(v.get("user_id")) == str(user_id)}
    active_file_ids = set(user_reg.keys())
    for fid in chat_history.get_active_file_ids(user_id=user_id):
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
            content=request.question,
            user_id=user_id
        )

        # Retrieve top chunks from ChromaDB (strictly user's active collection)
        chunks, metadatas, raw_sources = await asyncio.to_thread(
            vector_store.retrieve_top_chunks,
            doc_id=None if is_all else file_id,
            question=request.question,
            n_results=6 if is_all else 4,
            user_id=user_id
        )

        if is_all:
            source_files = list(dict.fromkeys([m.get("filename") for m in metadatas if m.get("filename")]))
            doc_filename = ", ".join(source_files) if source_files else "all uploaded documents"
        else:
            doc_info = user_reg.get(file_id, {})
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

        if not chunks:
            if is_all:
                if not user_reg or len(user_reg) == 0:
                    fallback_ans = "The information is not available. No documents found in your database. Please upload your files in the Documents tab first."
                else:
                    fallback_ans = "The information is not available in any of your currently active uploaded documents."
            elif file_id not in user_reg:
                fallback_ans = "The information is not available. The document is not in your active database."
            else:
                fallback_ans = "The information is not available in this document. Please try rephrasing your question."

            fallback_seq = await asyncio.to_thread(
                vector_store.get_suggested_questions,
                file_id or "all",
                llm_service,
                user_id
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
                suggested_questions=fallback_seq[:3] if fallback_seq else [],
                user_id=user_id
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
            active_file_ids,
            user_id
        )

        # Generate answer using LLM
        answer = await asyncio.to_thread(
            llm_service.generate_answer,
            question=request.question,
            chunks=chunks,
            metadatas=metadatas,
            history=safe_history
        )

        # Generate sequential follow-up questions
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
            source_details=source_details,
            user_id=user_id
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
            is_error=True,
            user_id=user_id
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
async def get_sequential_questions_endpoint(
    request: SequentialQuestionsRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Suggests sequential follow-up questions using LLM based on user's document.
    """
    if not request.doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question cannot be empty")

    user_id = current_user["id"]
    reg = vector_store._get_registry()
    doc_info = reg.get(request.doc_id, {})
    if doc_info and doc_info.get("user_id") and str(doc_info.get("user_id")) != str(user_id):
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this document.")

    doc_filename = doc_info.get("filename", "document")

    chunks, _, _ = await asyncio.to_thread(
        vector_store.retrieve_top_chunks,
        doc_id=request.doc_id,
        question=request.question,
        n_results=4,
        user_id=user_id
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
async def get_document_chat(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns persistent chat messages for doc_id or chat_id for backward compatibility.
    """
    clean_id = doc_id.strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="doc_id cannot be empty")

    user_id = current_user["id"]
    reg = vector_store._get_registry()

    if clean_id != "all":
        # Check if clean_id is in registry
        if clean_id in reg:
            doc_owner = reg[clean_id].get("user_id")
            if doc_owner and str(doc_owner) != str(user_id):
                raise HTTPException(status_code=403, detail="Forbidden: You do not own this document.")
        else:
            # Check if clean_id is a chat_session
            sess = await asyncio.to_thread(chat_history.get_session, clean_id, user_id)
            if not sess:
                # Check files table
                file_any = await asyncio.to_thread(chat_history.get_file, clean_id, None)
                if file_any and file_any.get("user_id") and str(file_any.get("user_id")) != str(user_id):
                    raise HTTPException(status_code=403, detail="Forbidden: You do not own this document.")

    messages = await asyncio.to_thread(chat_history.get_messages, clean_id, user_id)
    return {
        "doc_id": clean_id,
        "messages": messages,
        "source": "sqlite"
    }
