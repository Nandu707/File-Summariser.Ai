import os
import re
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

STRICT_CONTEXT_SYSTEM_PROMPT = """You are a helpful and accurate document question-answering assistant.
Your task is to answer the user's question based on the provided document context excerpts below.

CRITICAL RULES:
1. Base your answer on the provided context excerpts below.
2. If the user asks for a summary, overview, or explanation of the document, provide a clear, concise summary using the facts and points present in the excerpts.
3. If the user asks a specific question, find the relevant information in the excerpts and answer it directly.
4. Whenever citing facts, include the corresponding source page number in parentheses (e.g., "(Page 2)").
5. Keep your answer factual, direct, and concise.
6. Always try your best to answer from the context. Even if the context is only partially relevant, extract and present whatever useful information is available.
7. Only say you cannot find the answer if the context excerpts contain absolutely no information related to the question at all.
"""

class LLMService:
    def __init__(self, gemini_api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

    def format_context(self, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> str:
        """Formats top 4 chunks with page metadata into structured context."""
        context_parts = []
        for idx, chunk in enumerate(chunks):
            page_num = "Unknown"
            if metadatas and idx < len(metadatas) and isinstance(metadatas[idx], dict):
                page_num = metadatas[idx].get("page", "Unknown")
            context_parts.append(f"[Excerpt {idx + 1} | Page {page_num}]:\n{chunk.strip()}")
        return "\n\n".join(context_parts)

    def generate_answer(self, question: str, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Passes retrieved chunks to the LLM with a strict context-only prompt,
        returning the answer.
        """
        if not chunks:
            return "I cannot find the answer in the provided document context."

        context_str = self.format_context(chunks, metadatas)

        prompt = (
            f"{STRICT_CONTEXT_SYSTEM_PROMPT}\n\n"
            f"--- PROVIDED CONTEXT (TOP 4 CHUNKS) ---\n"
            f"{context_str}\n"
            f"--- END OF CONTEXT ---\n\n"
            f"Question: {question}\n\n"
            f"Strict Context-Only Answer:"
        )

        # 1. Google Gemini API (if key configured)
        if self.gemini_api_key:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=self.gemini_api_key)
                for model_name in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"]:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.0,
                            )
                        )
                        if response and response.text:
                            return response.text.strip()
                    except Exception as model_err:
                        print(f"[LLMService] Model {model_name} error: {model_err}")
                        continue
            except Exception as e:
                print(f"[LLMService] Gemini generation error, falling back: {e}")

        # 2. OpenAI API (if key configured)
        if self.openai_api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_api_key)
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": STRICT_CONTEXT_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {question}"}
                    ],
                    temperature=0.0,
                )
                content = res.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as e:
                print(f"[LLMService] OpenAI generation error, falling back: {e}")

        # 3. Built-in Strict Context-Only Grounded Fallback (Runs 100% offline with zero external API key requirements)
        return self._strict_context_grounded_answer(question, chunks, metadatas)

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
                bullet_points = "\n".join([f"- **(Page {it['page']})**: \"{it['sentence']}\"" for it in fallback_sentences])
                pages_str = ", ".join(f"Page {p}" for p in sorted(list(set(it['page'] for it in fallback_sentences))))
                return f"Based on the most relevant excerpts from the document ({pages_str}):\n\n{bullet_points}\n\n*These are the closest matching sections retrieved from the document.*"
            # Absolute last resort: show raw chunk content
            if chunks:
                first_chunk = chunks[0].strip()[:500]
                page_num = metadatas[0].get("page", 1) if metadatas and isinstance(metadatas[0], dict) else 1
                return f"Based on the document content (Page {page_num}):\n\n> {first_chunk}\n\n*This is the most relevant section found in the document.*"

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

        bullet_points = "\n".join([f"- (Page {it['page']}): \"{it['sentence']}\"" for it in selected])
        pages_str = ", ".join(f"Page {p}" for p in sorted(list(pages_cited)))

        return (
            f"Based strictly on the provided context ({pages_str}):\n\n"
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
        if self.gemini_api_key:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=self.gemini_api_key)
                for model_name in ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-latest"]:
                    try:
                        res = client.models.generate_content(
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
        if self.openai_api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_api_key)
                res = client.chat.completions.create(
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
        questions = []

        if any(term in fn_lower or term in text_corpus for term in ["resume", "cv", "candidate", "engineer", "experience", "education"]):
            questions.append(f"What are the candidate's core technical skills and qualifications?")
            questions.append(f"What work experience, internships, and key projects are detailed?")
            questions.append(f"What degrees, certifications, or educational background are listed?")
            questions.append(f"What tools, frameworks, and technologies is the candidate experienced with?")
        elif any(term in fn_lower or term in text_corpus for term in ["report", "project", "system", "architecture", "design", "development", "implementation"]):
            questions.append(f"What is the main problem statement and scope of this project?")
            questions.append(f"What system architecture, modules, and database structures are described?")
            questions.append(f"What technologies, frameworks, and APIs are implemented?")
            questions.append(f"What are the major conclusions, test results, and next steps?")
        elif any(term in fn_lower or term in text_corpus for term in ["abstract", "research", "paper", "quantum", "algorithm", "study"]):
            questions.append(f"What is the central research objective and methodology?")
            questions.append(f"What key algorithms, models, or experiments are discussed?")
            questions.append(f"What are the primary findings and demonstrated results?")
            questions.append(f"What future research directions or applications are proposed?")
        else:
            base_name = re.sub(r"\.[a-zA-Z0-9]+$", "", filename)
            questions.append(f"What is the main purpose and summary of {base_name}?")
            questions.append(f"What key metrics, details, or statistics are outlined in this document?")
            questions.append(f"What are the primary takeaways and conclusions?")

        return questions[:4]


# Default singleton instance
_default_llm_service = None

def get_llm_service() -> LLMService:
    global _default_llm_service
    if _default_llm_service is None:
        _default_llm_service = LLMService()
    return _default_llm_service

def generate_answer(question: str, chunks: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> str:
    return get_llm_service().generate_answer(question, chunks, metadatas)
