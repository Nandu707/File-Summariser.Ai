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

def is_no_info_answer(answer: str) -> bool:
    """Returns True if the LLM response indicates that documents do not contain information about the question."""
    if not answer or not isinstance(answer, str):
        return False
    text = answer.strip().lower()
    no_info_patterns = [
        r"do not contain any information",
        r"does not contain any information",
        r"do not contain information",
        r"does not contain information",
        r"contain no information",
        r"contains no information",
        r"provide no information",
        r"provides no information",
        r"not in any uploaded",
        r"not in the uploaded",
        r"not available in any of the uploaded",
        r"not available in this document",
        r"not available in the uploaded",
        r"not found in the provided",
        r"not found in any of the provided",
        r"no information (?:is )?(?:found|available|provided|detailed)?.*(?:in|from) the provided",
        r"no information (?:is )?(?:found|available|provided|detailed)?.*(?:in|from) any of the",
        r"there (?:is|are) no (?:specific )?(?:information|details|mention|instructions)",
        r"(?:provided|uploaded) (?:documents?|files?|excerpts?|context) (?:do|does) not (?:contain|mention|have|provide|detail)",
        r"(?:documents?|files?|excerpts?|context) (?:do|does) not (?:contain|mention|have|provide|detail) any information",
        r"(?:documents?|files?|excerpts?|context) (?:do|does) not (?:contain|mention|have|provide|detail) information",
        r"(?:documents?|files?|excerpts?) provided (?:do|does) not (?:contain|mention|have|provide|detail)",
        r"none of the (?:provided|uploaded) (?:documents?|files?|excerpts?) (?:contain|mention|have|provide)",
        r"could not find any information",
        r"cannot find any information",
        r"based on the (?:uploaded|provided) (?:documents?|files?|excerpts?),? there (?:is|are) no",
        r"(?:does|do) not have any information",
        r"not mentioned in the (?:provided|uploaded)",
        r"cannot be answered (?:from|based on) the (?:provided|uploaded)",
    ]
    for pattern in no_info_patterns:
        if re.search(pattern, text):
            return True
    return False

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
    # NOTE: User chats are strictly private to each user. Admin cannot view user chats.

    # Ensure active shared registry documents are registered in files table
    reg = vector_store._get_registry()
    for did, dinfo in reg.items():
        chat_history.register_file(did, dinfo.get("filename", "Document"), status="active")

    # Clean up any duplicate empty "All files" sessions for this user
    try:
        with chat_history._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM chat_sessions 
                WHERE user_id = ? 
                  AND scope = 'all' 
                  AND (SELECT COUNT(*) FROM messages WHERE chat_id = chat_sessions.id) = 0
                  AND id NOT IN (
                      SELECT id FROM chat_sessions 
                      WHERE user_id = ? AND scope = 'all' 
                      ORDER BY updated_at DESC LIMIT 1
                  )
            """, (str(user_id), str(user_id)))
            conn.commit()
    except Exception:
        pass

    sessions = await asyncio.to_thread(chat_history.get_sessions, search_query=q, user_id=user_id)
    return sessions

@router.post("/api/chats")
async def create_chat_session(
    request: CreateChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Creates a new chat session for the current user.
    User can choose scope ('all' or a specific active admin file_id).
    Strictly private to current_user.
    """
    user_id = current_user["id"]
    # NOTE: User chats are strictly private to each user. Admin cannot view user chats.
    reg = vector_store._get_registry()
    file_id = request.file_id
    file_name = request.file_name

    if request.scope == "file":
        if not file_id:
            raise HTTPException(status_code=400, detail="file_id is required when scope is 'file'")
        
        file_rec = chat_history.get_file(file_id)
        if file_rec and file_rec.get("status") == "deleted":
            raise HTTPException(status_code=400, detail="Cannot create a new chat for a deleted file.")

        if not file_name:
            doc_info = reg.get(file_id, {})
            file_name = doc_info.get("filename", "Document")

    # Clean up any unstarted empty sessions for this user so old unused drafts don't accumulate
    try:
        with chat_history._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM chat_sessions 
                WHERE user_id = ? 
                  AND (SELECT COUNT(*) FROM messages WHERE chat_id = chat_sessions.id) = 0
            """, (str(user_id),))
            conn.commit()
    except Exception:
        pass

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
    # NOTE: User chats are strictly private to each user. Admin cannot view user chats.
    session = await asyncio.to_thread(chat_history.get_session, chat_id, user_id)
    if not session:
        # If chat_id is 'all' or matches an active shared document, find existing session or create on-the-fly
        reg = vector_store._get_registry()
        if chat_id in ("all", "*"):
            all_sessions = await asyncio.to_thread(chat_history.get_sessions, None, user_id)
            existing_all = next((s for s in all_sessions if s.get("scope") == "all"), None)
            if existing_all:
                session = existing_all
            else:
                session = await asyncio.to_thread(chat_history.create_session, scope="all", title="All files", user_id=user_id)
        elif chat_id in reg:
            fn = reg[chat_id].get("filename", "Document")
            file_sessions = await asyncio.to_thread(chat_history.get_sessions, None, user_id)
            existing_file = next((s for s in file_sessions if s.get("scope") == "file" and s.get("file_id") == chat_id), None)
            if existing_file:
                session = existing_file
            else:
                session = await asyncio.to_thread(chat_history.create_session, scope="file", file_id=chat_id, file_name=fn, title=fn, user_id=user_id)
        else:
            raise HTTPException(status_code=404, detail="Chat session not found or access denied")

    messages = await asyncio.to_thread(chat_history.get_messages, session["id"], user_id)
    for m in messages:
        if m.get("role") == "assistant" and is_no_info_answer(m.get("content", "")):
            m["sources"] = []
            m["source_details"] = []
            m["source_documents"] = []
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
    Renames or updates scope/file of a chat session owned by current user.
    """
    if not chat_id.strip():
        raise HTTPException(status_code=400, detail="chat_id cannot be empty")

    user_id = current_user["id"]
    # NOTE: User chats are strictly private to each user. Admin cannot view user chats.
    clean_title = request.title.strip() if request.title else None
    clean_scope = request.scope.strip() if request.scope else None
    clean_file_id = request.file_id.strip() if request.file_id else None
    clean_file_name = request.file_name.strip() if request.file_name else None

    if clean_scope == "file" and clean_file_id and not clean_file_name:
        reg = vector_store._get_registry()
        clean_file_name = reg.get(clean_file_id, {}).get("filename", "Document")

    # If updating scope/file, call update_session
    if hasattr(chat_history, "update_session"):
        success = await asyncio.to_thread(
            chat_history.update_session,
            chat_id=chat_id,
            title=clean_title,
            scope=clean_scope,
            file_id=clean_file_id,
            file_name=clean_file_name,
            user_id=user_id
        )
    else:
        success = False

    if not success and clean_title:
        success = await asyncio.to_thread(chat_history.update_session_title, chat_id, clean_title, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found or could not be updated")

    return {
        "id": chat_id,
        "title": clean_title,
        "scope": clean_scope,
        "file_id": clean_file_id,
        "file_name": clean_file_name,
        "status": "updated"
    }

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
    # NOTE: User chats are strictly private to each user. Admin cannot view user chats.
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

@router.delete("/api/chats/{chat_id}/messages/{message_id}")
async def delete_chat_message(
    chat_id: str,
    message_id: int,
    truncate: bool = Query(False, description="If true, deletes all messages from this message onwards"),
    current_user: dict = Depends(get_current_user)
):
    """
    Deletes a specific user question (and its assistant answer), or truncates the conversation
    from that turn onwards (used for undo and edit features).
    Strictly verified by current user ownership.
    """
    user_id = current_user["id"]
    success = await asyncio.to_thread(
        chat_history.delete_message_turn,
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        truncate=truncate
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or unauthorized to delete"
        )
    return {
        "status": "deleted",
        "chat_id": chat_id,
        "message_id": message_id,
        "truncated": truncate
    }

# ==========================================
# QUESTION / ANSWER ENDPOINT
# ==========================================

@router.post("/api/ask", response_model=AskResponse)
@router.post("/api/chats/ask", response_model=AskResponse)
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
    # NOTE: User chats are strictly private to each user. Admin cannot view user chats.

    # 1. Resolve session and scope
    session = None
    target_chat_id = request.chat_id
    raw_doc_id = (request.doc_id or "all").strip()

    if target_chat_id and target_chat_id not in ("all", "new", "*"):
        session = await asyncio.to_thread(chat_history.get_session, target_chat_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found or access denied.")

    if not session:
        # Fall back to resolving by doc_id or creating fresh session
        if raw_doc_id in ("all", "*", ""):
            session = await asyncio.to_thread(chat_history.create_session, scope="all", title="New chat", user_id=user_id)
        else:
            reg = vector_store._get_registry()
            if raw_doc_id not in reg and not chat_history.get_file(raw_doc_id):
                raise HTTPException(status_code=404, detail="Document not found.")

            doc_info = reg.get(raw_doc_id, {})
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
        if chat_history.is_file_deleted(file_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This file has been deleted. Chat is read-only."
            )

    # 3. Get active files from registry and files table for the shared admin store
    reg = vector_store._get_registry()
    active_file_ids = set(reg.keys())
    for fid in chat_history.get_active_file_ids():
        active_file_ids.add(fid)

    thread_filename = session.get("file_name") or ("All files" if is_all else "Document")

    try:
        # Store user question in SQLite
        user_msg = await asyncio.to_thread(
            chat_history.add_message,
            chat_id=effective_chat_id,
            doc_id=file_id or "all",
            filename=thread_filename,
            role="user",
            content=request.question,
            user_id=user_id
        )

        is_retry = bool(getattr(request, "is_retry", False))

        # Retrieve top chunks from ChromaDB from the shared active admin files
        n_chunks = (10 if is_all else 7) if is_retry else (6 if is_all else 4)
        chunks, metadatas, raw_sources = await asyncio.to_thread(
            vector_store.retrieve_top_chunks,
            doc_id=None if is_all else file_id,
            question=request.question,
            n_results=n_chunks
        )

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

        if not chunks:
            if is_all:
                if not reg or len(reg) == 0:
                    fallback_ans = "The information is not available. No documents found in your database. Please upload your files in the Documents tab first."
                else:
                    fallback_ans = "The information is not available in any of the uploaded documents."
            elif file_id not in reg:
                fallback_ans = "The information is not available. The document is not in the active database."
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
                suggested_questions=fallback_seq[:3] if fallback_seq else [],
                user_id=user_id
            )
            return {
                "answer": fallback_ans,
                "sources": [],
                "source_documents": [],
                "source_details": [],
                "suggested_questions": fallback_seq[:3] if fallback_seq else [],
                "chat_id": effective_chat_id
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
            history=safe_history,
            is_retry=is_retry
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

        if is_no_info_answer(answer):
            retained_metas = []
        else:
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

        sorted_sources = sorted(list(set(grounded_source_pages))) if not is_no_info_answer(answer) else []
        source_details = grounded_source_details if not is_no_info_answer(answer) else []
        source_files = list(grounded_source_files) if not is_no_info_answer(answer) else []

        # Store assistant response in persistent SQLite database
        bot_msg = await asyncio.to_thread(
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
            "suggested_questions": sequential_questions,
            "chat_id": effective_chat_id,
            "user_message_id": user_msg.get("id") if isinstance(user_msg, dict) else None,
            "assistant_message_id": bot_msg.get("id") if isinstance(bot_msg, dict) else None
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
    for m in messages:
        if m.get("role") == "assistant" and is_no_info_answer(m.get("content", "")):
            m["sources"] = []
            m["source_details"] = []
            m["source_documents"] = []
    return {
        "doc_id": clean_id,
        "messages": messages,
        "source": "sqlite"
    }
