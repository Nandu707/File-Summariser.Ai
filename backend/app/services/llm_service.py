import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple, Union
from dotenv import load_dotenv

load_dotenv()

STRICT_CONTEXT_SYSTEM_PROMPT = """You are given content from multiple uploaded files, each labelled with its file name. Answer using information from ALL relevant files. If a question spans several files, combine them. State which file each part of the answer comes from. If the answer is not in any uploaded file, say so instead of guessing."""

class LLMService:
    GEMINI_MODELS = [
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash"
    ]

    def __init__(self, gemini_api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._gemini_client = None
        self._openai_client = None

    def _get_gemini_client(self):
        current_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if self._gemini_client is None and current_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=current_key)
                self.gemini_api_key = current_key
            except Exception as e:
                print(f"[LLMService] Error initializing Gemini client: {e}")
        return self._gemini_client

    def _get_openai_client(self):
        if self._openai_client is None and self.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.openai_api_key)
            except Exception as e:
                print(f"[LLMService] Error initializing OpenAI client: {e}")
        return self._openai_client

    def format_context(self, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> str:
        """Formats chunks with filename and page metadata into structured context."""
        context_parts = []
        for idx, chunk in enumerate(chunks):
            page_num = "Unknown"
            file_name = ""
            if metadatas and idx < len(metadatas) and isinstance(metadatas[idx], dict):
                page_num = metadatas[idx].get("page", "Unknown")
                file_name = metadatas[idx].get("filename", "")
            file_label = f"Document: {file_name} | " if file_name else ""
            context_parts.append(f"[Excerpt {idx + 1} | {file_label}Page {page_num}]:\n{chunk.strip()}")
        return "\n\n".join(context_parts)

    def generate_answer(
        self,
        question: str,
        chunks: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Passes retrieved chunks to the LLM with a strict context-only prompt,
        returning the answer. Primary: Google Gemini; Secondary: OpenAI; Fallback: offline grounded.
        Includes leak-free conversation history if provided.
        """
        if not chunks:
            return "The answer is not in any uploaded file."

        context_str = self.format_context(chunks, metadatas)

        # Build list of available files to pass to LLM
        available_files = []
        if metadatas:
            for m in metadatas:
                if isinstance(m, dict):
                    fn = m.get("filename")
                    if fn and fn not in available_files:
                        available_files.append(fn)
        files_list_str = ", ".join(available_files) if available_files else "None"

        # Format conversation history if available
        history_str = ""
        if history and len(history) > 0:
            hist_parts = []
            for h in history[-6:]: # Limit to last 6 turns for prompt efficiency
                role = "User" if h.get("role") == "user" else "Assistant"
                hist_parts.append(f"{role}: {h.get('content', '').strip()}")
            if hist_parts:
                history_str = "\n\n--- PREVIOUS CONVERSATION (ACTIVE FILES ONLY) ---\n" + "\n".join(hist_parts) + "\n--- END CONVERSATION ---\n"

        prompt = (
            f"{STRICT_CONTEXT_SYSTEM_PROMPT}\n\n"
            f"Available uploaded files: {files_list_str}\n\n"
            f"--- PROVIDED FILE EXCERPTS ---\n"
            f"{context_str}\n"
            f"--- END OF EXCERPTS ---\n"
            f"{history_str}\n"
            f"Question: {question}\n\n"
            f"Answer:"
        )

        ans = None
        # 1. Google Gemini API (if key configured)
        gemini_client = self._get_gemini_client()
        if gemini_client:
            try:
                from google.genai import types
                for model_name in self.GEMINI_MODELS:
                    try:
                        response = gemini_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.0,
                            )
                        )
                        if response and response.text:
                            ans = response.text.strip()
                            break
                    except Exception as model_err:
                        print(f"[LLMService] Model {model_name} error: {model_err}")
                        continue
            except Exception as e:
                print(f"[LLMService] Gemini generation error, falling back: {e}")

        # 2. OpenAI API (if key configured)
        openai_client = self._get_openai_client()
        if not ans and openai_client:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_api_key)
                messages_payload = [{"role": "system", "content": STRICT_CONTEXT_SYSTEM_PROMPT}]
                if history:
                    for h in history[-6:]:
                        messages_payload.append({"role": h.get("role", "user"), "content": h.get("content", "")})
                messages_payload.append({"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"})

                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages_payload,
                    temperature=0.0,
                )
                content = res.choices[0].message.content
                if content:
                    ans = content.strip()
            except Exception as e:
                print(f"[LLMService] OpenAI generation error, falling back: {e}")

        # 3. Built-in Strict Context-Only Grounded Fallback (Runs 100% offline with zero external API key requirements)
        if not ans:
            ans = self._strict_context_grounded_answer(question, chunks, metadatas)

        return self._clean_page_numbers_from_answer(ans)

    def _clean_page_numbers_from_answer(self, text: str) -> str:
        """Removes any page citations or page number references from the text."""
        if not text:
            return text
        # Remove parenthetical page references, e.g., (Page 1), (Pages 1-3), (p. 2), [Page 1], (Page 1, 2)
        cleaned = re.sub(r"\s*[\(\[]\s*(?:Page|Pages|p\.|pp\.)\s*\d+(?:\s*[-–,]\s*\d+)*\s*[\)\]]", "", text, flags=re.IGNORECASE)
        # Remove bolded or prefix page markers like "- **(Page 1)**:" or "- (Page 1):" or "- Page 1:"
        cleaned = re.sub(r"^\s*[-*•]\s*(?:\*\*)?\(?(?:Page|Pages|p\.|pp\.)\s*\d+(?:\s*[-–,]\s*\d+)*\)?(?:\*\*)?:?\s*", "- ", cleaned, flags=re.MULTILINE | re.IGNORECASE)
        # Remove standalone "Page X:" or "Page X -" at start of lines
        cleaned = re.sub(r"^\s*(?:Page|Pages)\s*\d+(?:\s*[-–,]\s*\d+)*:?\s*", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
        # Clean up any trailing / empty parentheses like " ()"
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        cleaned = re.sub(r"\[\s*\]", "", cleaned)
        # Clean up repeated spaces
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        return cleaned.strip()

    def _strict_context_grounded_answer(self, question: str, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Synthesizes a strict context-grounded answer based strictly on the retrieved top chunks.
        When no LLM API is available, this provides the best possible offline answer.
        """
        q_tokens = set(re.findall(r"\w+", question.lower()))
        stopwords = {
            "what", "is", "the", "a", "an", "and", "or", "in", "on", "of", "to", "for", 
            "with", "how", "why", "who", "where", "can", "does", "do", "explain", "describe", 
            "tell", "me", "about", "are", "by", "from", "at", "as", "which", "this",
            "that", "it", "its", "was", "were", "be", "been", "being", "have", "has",
            "had", "will", "would", "could", "should", "may", "might", "shall",
            "not", "no", "yes", "but", "if", "then", "so", "than", "very", "just",
            "also", "any", "all", "each", "every", "some", "many", "much", "more",
            "most", "other", "into", "through", "during", "before", "after", "above",
            "below", "between", "out", "up", "down", "over", "under", "again", "further"
        }
        keywords = {t for t in q_tokens if t not in stopwords and len(t) > 2}

        matched_sentences = []
        for idx, chunk in enumerate(chunks):
            page_num = 1
            if metadatas and idx < len(metadatas) and isinstance(metadatas[idx], dict):
                page_num = metadatas[idx].get("page", 1)

            # Break chunk into sentences
            sentences = re.split(r"(?<=[.!?])\s+", chunk.replace("\n", " "))
            for sent in sentences:
                sent_clean = sent.strip()
                if len(sent_clean) < 15:
                    continue
                s_tokens = set(re.findall(r"\w+", sent_clean.lower()))
                overlap = len(keywords.intersection(s_tokens))
                if overlap > 0:
                    matched_sentences.append({
                        "sentence": sent_clean,
                        "page": page_num,
                        "score": overlap,
                        "len": len(sent_clean)
                    })

        if not matched_sentences:
            # No keyword overlap found — provide the most relevant chunk content directly
            # instead of refusing to answer. The chunks were already semantically retrieved
            # by ChromaDB, so they ARE the most relevant content.
            fallback_sentences = []
            for idx, chunk in enumerate(chunks):
                page_num = 1
                if metadatas and idx < len(metadatas) and isinstance(metadatas[idx], dict):
                    page_num = metadatas[idx].get("page", 1)
                # Get all meaningful sentences from the chunk
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", chunk.replace("\n", " ")) if len(s.strip()) > 20]
                for sent in sentences[:2]:  # Take top 2 sentences per chunk
                    fallback_sentences.append({"sentence": sent, "page": page_num})
                if len(fallback_sentences) >= 5:
                    break
            if fallback_sentences:
                bullet_points = "\n".join([f"- \"{it['sentence']}\"" for it in fallback_sentences])
                return f"Based on the most relevant excerpts from the document:\n\n{bullet_points}\n\n*These are the closest matching sections retrieved from the document.*"
            # Absolute last resort: show raw chunk content
            if chunks:
                first_chunk = chunks[0].strip()[:500]
                return f"Based on the document content:\n\n> {first_chunk}\n\n*This is the most relevant section found in the document.*"

        # Sort sentences by keyword score
        matched_sentences.sort(key=lambda s: (-s["score"], s["len"]))

        # Collect unique statements
        selected = []
        seen = set()
        pages_cited = set()
        for item in matched_sentences:
            clean = item["sentence"]
            if clean not in seen:
                seen.add(clean)
                selected.append(item)
                pages_cited.add(item["page"])
                if len(selected) >= 3:
                    break

        bullet_points = "\n".join([f"- \"{it['sentence']}\"" for it in selected])

        return (
            f"Based strictly on the provided context:\n\n"
            f"{bullet_points}"
        )

    def generate_suggested_questions(self, filename: str, sample_chunks: List[str]) -> List[str]:
        """
        Generates 3 to 4 document-specific, variable suggested questions based on the document excerpts.
        """
        if not sample_chunks:
            return self._generate_heuristic_suggested_questions(filename, [])

        context_snippet = "\n\n".join(sample_chunks)[:2500]
        prompt = (
            f"You are an intelligent document analyst.\n"
            f"Analyze the following excerpts from the uploaded document \"{filename}\":\n\n"
            f"--- DOCUMENT EXCERPTS ---\n"
            f"{context_snippet}\n"
            f"--- END EXCERPTS ---\n\n"
            f"Generate 3 to 4 concise, specific, and engaging questions that a user would naturally want to ask about this specific document.\n\n"
            f"CRITICAL RULES:\n"
            f"1. Make each question specific to the actual subjects, projects, methodologies, metrics, or entities mentioned in the document.\n"
            f"2. DO NOT generate generic questions like 'What is this document about?'.\n"
            f"3. Return ONLY a valid JSON array of 3 or 4 strings, with no markdown code fences, comments, or extra text.\n"
            f"Example format:\n"
            f"[\"What AWS services and Python frameworks are featured?\", \"What are the main database entities in the ER diagram?\"]"
        )

        # 1. Google Gemini
        gemini_client = self._get_gemini_client()
        if gemini_client:
            try:
                from google.genai import types
                for model_name in self.GEMINI_MODELS:
                    try:
                        res = gemini_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.3,
                                response_mime_type="application/json"
                            )
                        )
                        if res and res.text:
                            raw = res.text.strip()
                            if raw.startswith("```"):
                                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                                raw = re.sub(r"\s*```$", "", raw)
                            parsed = json.loads(raw)
                            if isinstance(parsed, list) and len(parsed) >= 2:
                                return [str(q).strip() for q in parsed if str(q).strip()][:4]
                            elif isinstance(parsed, dict):
                                for val in parsed.values():
                                    if isinstance(val, list) and len(val) >= 2:
                                        return [str(q).strip() for q in val if str(q).strip()][:4]
                    except Exception as model_err:
                        continue
            except Exception as e:
                print(f"[LLMService] Gemini suggestions notice: {e}")

        # 2. OpenAI
        openai_client = self._get_openai_client()
        if openai_client:
            try:
                res = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You output only a JSON array of 3 to 4 specific questions about the provided document context."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                raw = res.choices[0].message.content
                if raw:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        for val in parsed.values():
                            if isinstance(val, list) and len(val) >= 2:
                                return [str(q).strip() for q in val if str(q).strip()][:4]
                    elif isinstance(parsed, list) and len(parsed) >= 2:
                        return [str(q).strip() for q in parsed if str(q).strip()][:4]
            except Exception as e:
                print(f"[LLMService] OpenAI suggestions notice: {e}")

        # 3. Dynamic Heuristic Fallback
        return self._generate_heuristic_suggested_questions(filename, sample_chunks)

    def _generate_heuristic_suggested_questions(self, filename: str, sample_chunks: List[str]) -> List[str]:
        text_corpus = " ".join(sample_chunks).lower()
        fn_lower = filename.lower()
        base_name = re.sub(r"\.[a-zA-Z0-9]+$", "", filename)
        questions = []

        # Check if genuinely a resume / CV
        is_resume = (
            any(term in fn_lower for term in ["resume", "cv", "curriculum_vitae", "biodata"]) or
            ("curriculum vitae" in text_corpus) or
            ("technical skills" in text_corpus and "work experience" in text_corpus and "education" in text_corpus and "candidate" in text_corpus)
        )

        if is_resume:
            questions.append("What are the candidate's core technical skills and qualifications?")
            questions.append("What work experience, internships, and key projects are detailed?")
            questions.append("What degrees, certifications, or educational background are listed?")
            questions.append("What tools, frameworks, and technologies is the candidate experienced with?")
            return questions[:4]

        # Extract meaningful named entities or topics from sample chunks
        combined_samples = " ".join(sample_chunks)
        entity_matches = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{2,}(?:\s+[A-Z][a-zA-Z0-9_\-]+)?\b", combined_samples)
        common_words = {
            "the", "this", "that", "these", "those", "from", "with", "have", "been", "were",
            "page", "pages", "document", "chapter", "section", "table", "figure", "index",
            "author", "title", "rights", "reserved", "copyright", "published", "edition",
            "william", "enter", "exit", "scene", "public"
        }
        entities = []
        for em in entity_matches:
            clean_em = em.strip()
            if clean_em.lower() not in common_words and len(clean_em) > 2:
                if clean_em not in entities and clean_em.lower() not in [e.lower() for e in entities]:
                    entities.append(clean_em)
                if len(entities) >= 4:
                    break

        # Check document category
        if any(term in fn_lower or term in text_corpus for term in ["play", "act ", "scene ", "tragedy", "comedy", "novel", "poem", "story", "shakespeare"]):
            if len(entities) >= 2:
                questions.append(f"What key events and conflicts involve {entities[0]} in {base_name}?")
                questions.append(f"How do {entities[0]} and {entities[1]} interact throughout the text?")
                questions.append(f"What are the central themes, plot developments, and settings described in {base_name}?")
            else:
                questions.append(f"What is the central story, setting, and main conflict in {base_name}?")
                questions.append(f"Who are the primary characters and what motivates them?")
                questions.append(f"What are the major plot developments and climax in {base_name}?")
        elif any(term in fn_lower or term in text_corpus for term in ["report", "project", "system", "architecture", "design", "development", "implementation", "vitallink", "framework", "api"]):
            if len(entities) >= 2:
                questions.append(f"What is the core objective and architecture of {entities[0]}?")
                questions.append(f"How does {entities[0]} utilize or integrate with {entities[1]}?")
                questions.append(f"What are the key technical specifications and outcomes described in {base_name}?")
            else:
                questions.append(f"What is the main problem statement and scope of {base_name}?")
                questions.append(f"What system architecture, modules, and database structures are described?")
                questions.append(f"What technologies, frameworks, and APIs are implemented?")
                questions.append(f"What are the major conclusions and test results in {base_name}?")
        elif any(term in fn_lower or term in text_corpus for term in ["abstract", "research", "paper", "quantum", "algorithm", "study", "analysis"]):
            if len(entities) >= 1:
                questions.append(f"What is the central research methodology and role of {entities[0]} in {base_name}?")
            else:
                questions.append(f"What is the central research objective and methodology of {base_name}?")
            questions.append(f"What key algorithms, models, or experimental findings are presented?")
            questions.append(f"What primary conclusions, metrics, and future directions are proposed?")
        else:
            if len(entities) >= 2:
                questions.append(f"What key information regarding {entities[0]} is detailed in {base_name}?")
                questions.append(f"How is {entities[1]} explained or utilized in this document?")
                questions.append(f"What are the primary conclusions and takeaways from {base_name}?")
            elif len(entities) == 1:
                questions.append(f"What is the main discussion regarding {entities[0]} in {base_name}?")
                questions.append(f"What key data, facts, or statistics are outlined in {base_name}?")
                questions.append(f"What are the primary takeaways and recommendations?")
            else:
                questions.append(f"What is the main purpose and summary of {base_name}?")
                questions.append(f"What key facts, data, or findings are outlined in this document?")
                questions.append(f"What are the primary takeaways and conclusions from {base_name}?")

        return questions[:4]

    def generate_all_documents_suggested_questions(self, all_files_data: List[Dict[str, Any]]) -> List[str]:
        """
        Reads across all uploaded files and generates 4 to 6 relevant, specific questions
        spanning each uploaded document as well as comparative questions across documents.
        """
        if not all_files_data:
            return [
                "What topics and documents are available in the knowledge base?",
                "How do I query specific information across my uploaded files?"
            ]

        if len(all_files_data) == 1:
            return self.generate_suggested_questions(
                all_files_data[0].get("filename", "document"),
                all_files_data[0].get("chunks", [])
            )

        doc_summaries = []
        for idx, doc in enumerate(all_files_data):
            fn = doc.get("filename", f"Document {idx+1}")
            chunks = doc.get("chunks", [])
            preview_lines = []
            for c in chunks[:2]:
                cl = re.sub(r"^\[Page\s+\d+\]\s*", "", c).strip()
                if cl:
                    preview_lines.append(cl[:350])
            preview = "\n".join(preview_lines) if preview_lines else "General document content."
            doc_summaries.append(f"--- Document {idx + 1}: \"{fn}\" ---\n{preview}")

        combined_context = "\n\n".join(doc_summaries)

        prompt = (
            f"You are an intelligent knowledge base analyst assisting a user in a multi-document RAG system.\n"
            f"The user has uploaded {len(all_files_data)} documents to the system:\n\n"
            f"{combined_context}\n\n"
            f"Generate 4 to 6 concise, highly relevant, and engaging questions for the main chat page.\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. READ AND REPRESENT ALL UPLOADED FILES: Make sure questions cover the different files uploaded (e.g. at least one specific question highlighting each document's distinct topic, project, questions, or subjects).\n"
            f"2. Mention specific topics, technologies, problems, or entities from the files (e.g. project features, algorithms, programming questions, or story elements).\n"
            f"3. Include a question that synthesizes or compares topics across the uploaded files.\n"
            f"4. DO NOT generate generic questions like 'What is in file 1?' or 'Summarize all files'. Each question must be specific and directly answerable from the files.\n"
            f"5. Return ONLY a valid JSON array of 4 to 6 string questions, with no markdown code fences, comments, or extra text.\n"
            f"Example format:\n"
            f"[\"What is the system architecture of the Vital-Link blood donor project?\", \"How do you solve the Zoho number system problem using digits 3 and 4?\", \"How can you check a 5-digit number in C without using loops?\", \"What programming algorithms and frameworks are covered across the uploaded files?\"]"
        )

        # 1. Google Gemini
        gemini_client = self._get_gemini_client()
        if gemini_client:
            try:
                from google.genai import types
                for model_name in self.GEMINI_MODELS:
                    try:
                        res = gemini_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.3,
                                response_mime_type="application/json"
                            )
                        )
                        if res and res.text:
                            raw = res.text.strip()
                            if raw.startswith("```"):
                                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                                raw = re.sub(r"\s*```$", "", raw)
                            parsed = json.loads(raw)
                            if isinstance(parsed, list) and len(parsed) >= 2:
                                return [str(q).strip() for q in parsed if str(q).strip()][:6]
                            elif isinstance(parsed, dict):
                                for val in parsed.values():
                                    if isinstance(val, list) and len(val) >= 2:
                                        return [str(q).strip() for q in val if str(q).strip()][:6]
                    except Exception as model_err:
                        continue
            except Exception as e:
                print(f"[LLMService] Gemini multi-doc suggestions notice: {e}")

        # 2. OpenAI
        openai_client = self._get_openai_client()
        if openai_client:
            try:
                res = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You output only a JSON array of 4 to 6 specific questions representing all uploaded documents."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                raw = res.choices[0].message.content
                if raw:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        for val in parsed.values():
                            if isinstance(val, list) and len(val) >= 2:
                                return [str(q).strip() for q in val if str(q).strip()][:6]
                    elif isinstance(parsed, list) and len(parsed) >= 2:
                        return [str(q).strip() for q in parsed if str(q).strip()][:6]
            except Exception as e:
                print(f"[LLMService] OpenAI multi-doc suggestions notice: {e}")

        # 3. Dynamic Heuristic Fallback spanning all files
        fallback_questions = []
        for doc in all_files_data:
            fn = doc.get("filename", "")
            chunks = doc.get("chunks", [])
            q_list = self._generate_heuristic_suggested_questions(fn, chunks)
            if q_list:
                fallback_questions.append(q_list[0])

        if len(all_files_data) > 1:
            fallback_questions.append("What key concepts and methodologies are shared across all uploaded documents?")

        return fallback_questions[:6]

    def generate_sequential_questions(
        self,
        filename: str,
        question: str,
        answer: str,
        chunks: Optional[List[str]] = None
    ) -> List[str]:
        """
        Generates 3 logical sequential / follow-up questions tailored to the document content,
        the user's previous question, and the generated answer.
        """
        context_snippet = ""
        if chunks:
            context_snippet = "\n\n".join(chunks)[:2500]

        prompt = (
            f"You are an expert conversational AI document analyst.\n"
            f"The user is reading the document \"{filename}\" and just had the following Q&A interaction:\n\n"
            f"--- PREVIOUS QUESTION ---\n"
            f"{question}\n\n"
            f"--- PREVIOUS ANSWER ---\n"
            f"{answer}\n"
            f"--- END OF PREVIOUS INTERACTION ---\n\n"
            f"--- DOCUMENT EXCERPTS ---\n"
            f"{context_snippet}\n"
            f"--- END DOCUMENT EXCERPTS ---\n\n"
            f"Suggest 3 sequential follow-up questions that logically flow from this previous question and answer, "
            f"deeply relevant to the topics, methodologies, entities, and facts present in \"{filename}\".\n\n"
            f"CRITICAL RULES:\n"
            f"1. Progression: The questions must be natural next steps (e.g. drilling deeper into specific items mentioned in the answer, exploring related components described in the document, or asking about outcomes/implementation details).\n"
            f"2. Relevance: Directly connect the previous topic with other relevant information from the document excerpts.\n"
            f"3. Specificity: Be specific. Mention entities, technologies, sections, or metrics from the document. Do NOT ask generic questions like 'Can you elaborate?'.\n"
            f"4. Format: Return ONLY a valid JSON array of exactly 3 concise question strings, with no markdown code fences, comments, or extra text.\n"
            f"Example format:\n"
            f"[\"How were Lambda functions connected to S3?\", \"What IAM security policies were configured?\", \"What deployment pipelines were used for this setup?\"]"
        )

        # 1. Google Gemini API
        gemini_client = self._get_gemini_client()
        if gemini_client:
            try:
                from google.genai import types
                for model_name in self.GEMINI_MODELS:
                    try:
                        res = gemini_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.3,
                                response_mime_type="application/json"
                            )
                        )
                        if res and res.text:
                            raw = res.text.strip()
                            if raw.startswith("```"):
                                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                                raw = re.sub(r"\s*```$", "", raw)
                            parsed = json.loads(raw)
                            if isinstance(parsed, list) and len(parsed) >= 2:
                                return [str(q).strip() for q in parsed if str(q).strip()][:3]
                            elif isinstance(parsed, dict):
                                for val in parsed.values():
                                    if isinstance(val, list) and len(val) >= 2:
                                        return [str(q).strip() for q in val if str(q).strip()][:3]
                    except Exception as model_err:
                        continue
            except Exception as e:
                print(f"[LLMService] Gemini sequential questions notice: {e}")

        # 2. OpenAI API
        openai_client = self._get_openai_client()
        if openai_client:
            try:
                res = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You output only a JSON array of exactly 3 sequential follow-up questions."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                raw = res.choices[0].message.content
                if raw:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        for val in parsed.values():
                            if isinstance(val, list) and len(val) >= 2:
                                return [str(q).strip() for q in val if str(q).strip()][:3]
                    elif isinstance(parsed, list) and len(parsed) >= 2:
                        return [str(q).strip() for q in parsed if str(q).strip()][:3]
            except Exception as e:
                print(f"[LLMService] OpenAI sequential questions notice: {e}")

        # 3. Dynamic Heuristic Sequential Questions Fallback
        return self._generate_heuristic_sequential_questions(filename, question, answer, chunks)

    def _generate_heuristic_sequential_questions(
        self,
        filename: str,
        question: str,
        answer: str,
        chunks: Optional[List[str]] = None
    ) -> List[str]:
        """
        Offline fallback that generates 3 intelligent sequential questions strictly relatable
        to this file and the previous Q&A exchange.
        """
        base_name = re.sub(r"\.[a-zA-Z0-9]+$", "", filename)
        combined_text = f"{question} {answer}"
        if chunks:
            combined_text += " " + " ".join(chunks[:2])

        # Extract capitalized entities and significant terms (excluding grammar/stop words)
        words = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{2,}\b", combined_text)
        stopwords = {
            "what", "when", "where", "which", "with", "from", "that", "this", "these",
            "those", "have", "been", "were", "about", "could", "would", "should",
            "there", "their", "under", "after", "before", "page", "pages", "document",
            "based", "provided", "context", "excerpts", "answer", "question", "stated",
            "state", "according", "specific", "mentioned", "details", "information",
            "organization", "published", "edition", "also", "into", "more", "who", "whom",
            "whose", "why", "how", "does", "did", "can", "could", "will", "would", "shall",
            "are", "was", "has", "had", "tell", "give", "show", "list", "name", "find"
        }
        entities = []
        for w in words:
            clean = w.strip()
            if clean.lower() not in stopwords and len(clean) > 2:
                if clean not in entities and clean.lower() not in [e.lower() for e in entities]:
                    entities.append(clean)
                if len(entities) >= 3:
                    break

        questions = []
        if len(entities) >= 2:
            questions.append(f"What additional details about {entities[0]} are mentioned in {base_name}?")
            questions.append(f"How does {entities[0]} relate to {entities[1]} in the document?")
            questions.append(f"What further context or next steps regarding this topic are covered in {base_name}?")
        elif len(entities) == 1:
            questions.append(f"Can you provide more specific details about {entities[0]} in {base_name}?")
            questions.append(f"What background or significance does {entities[0]} hold in this text?")
            questions.append(f"What other findings or sections in {base_name} relate to this?")
        else:
            questions.append(f"Can you provide more detailed context about this point from {base_name}?")
            questions.append(f"What related findings or explanations are provided in {base_name}?")
            questions.append(f"What are the subsequent conclusions or outcomes discussed in {base_name}?")

        return questions[:3]


# Default singleton instance
_default_llm_service = None

def get_llm_service() -> LLMService:
    global _default_llm_service
    if _default_llm_service is None:
        _default_llm_service = LLMService()
    return _default_llm_service

def generate_answer(question: str, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> str:
    return get_llm_service().generate_answer(question, chunks, metadatas)

def generate_sequential_questions(filename: str, question: str, answer: str, chunks: Optional[List[str]] = None) -> List[str]:
    return get_llm_service().generate_sequential_questions(filename, question, answer, chunks)

