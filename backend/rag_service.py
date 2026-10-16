import os
import json
import uuid
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF
import chromadb
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
project_root = BASE_DIR.parent
root_vdb = project_root / "vector_db"
backend_vdb = BASE_DIR / "vector_db"
if root_vdb.exists() and (root_vdb / "chroma.sqlite3").exists():
    DEFAULT_VDB = str(root_vdb)
else:
    DEFAULT_VDB = str(backend_vdb)

VECTOR_DB_DIR = os.getenv("CHROMA_PERSIST_DIRECTORY", DEFAULT_VDB)
if not Path(VECTOR_DB_DIR).is_absolute():
    VECTOR_DB_DIR = str((project_root / VECTOR_DB_DIR).resolve())
DOCS_META_FILE = Path(VECTOR_DB_DIR) / "documents_registry.json"

class RAGService:
    def __init__(self, persist_dir: str = VECTOR_DB_DIR):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize persistent local chromadb client
        self.chroma_client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name="task_rag_vector_store",
            metadata={"description": "RAG document chunks with page metadata"}
        )
        self._ensure_registry()

    def _ensure_registry(self):
        if not DOCS_META_FILE.exists():
            with open(DOCS_META_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _get_registry(self) -> Dict[str, Any]:
        try:
            if DOCS_META_FILE.exists():
                with open(DOCS_META_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_registry(self, registry: Dict[str, Any]):
        try:
            with open(DOCS_META_FILE, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
        except Exception as e:
            print(f"[RAGService] Error saving document registry: {e}")

    def list_documents(self) -> List[Dict[str, Any]]:
        reg = self._get_registry()
        docs = list(reg.values())
        # Sort by upload time desc
        docs.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
        return docs

    def delete_document(self, doc_id: str) -> bool:
        try:
            # Delete chunks from ChromaDB
            self.collection.delete(where={"doc_id": doc_id})
            reg = self._get_registry()
            if doc_id in reg:
                del reg[doc_id]
                self._save_registry(reg)
            return True
        except Exception as e:
            print(f"[RAGService] Error deleting doc {doc_id}: {e}")
            return False

    def extract_text_with_metadata(self, filename: str, content: bytes) -> List[Dict[str, Any]]:
        """
        Extracts text page by page with metadata.
        Uses PyMuPDF (fitz) for PDFs as required.
        """
        ext = filename.lower().split(".")[-1]
        pages_data = []

        if ext == "pdf":
            # PyMuPDF extraction
            with fitz.open(stream=content, filetype="pdf") as doc:
                for page_idx in range(len(doc)):
                    page = doc[page_idx]
                    page_text = page.get_text("text") or ""
                    cleaned = self._clean_text(page_text)
                    if cleaned:
                        pages_data.append({
                            "page": page_idx + 1,
                            "text": cleaned
                        })
        elif ext in ["txt", "md"]:
            # Plain text / markdown extraction
            text = content.decode("utf-8", errors="replace")
            cleaned = self._clean_text(text)
            # TXT files can be divided into simulated pages by double newlines or form feeds if very large
            if "\x0c" in text:
                raw_pages = text.split("\x0c")
                for idx, p in enumerate(raw_pages):
                    cl = self._clean_text(p)
                    if cl:
                        pages_data.append({"page": idx + 1, "text": cl})
            else:
                # Chunk into virtual pages of ~3000 chars if long, otherwise single page
                if len(cleaned) > 4000:
                    virtual_pages = [cleaned[i:i + 3500] for i in range(0, len(cleaned), 3500)]
                    for idx, vp in enumerate(virtual_pages):
                        pages_data.append({"page": idx + 1, "text": vp})
                else:
                    pages_data.append({"page": 1, "text": cleaned})
        else:
            raise ValueError(f"Unsupported file format: .{ext}. Only .pdf and .txt files are supported.")

        return pages_data

    def _clean_text(self, text: str) -> str:
        # Normalize whitespace while preserving line structure
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def chunk_page_text(self, text: str, page_num: int, chunk_size: int = 600, overlap: int = 100) -> List[Dict[str, Any]]:
        """
        Chunks text with a sliding window approach with sentence boundary awareness.
        """
        chunks = []
        if not text:
            return chunks

        # Split into paragraphs or sentences
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        current_chunk = ""

        for p in paragraphs:
            if len(current_chunk) + len(p) + 1 <= chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + p
                else:
                    current_chunk = p
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # If paragraph itself is larger than chunk_size, split by sentences
                if len(p) > chunk_size:
                    sentences = re.split(r"(?<=[.!?])\s+", p)
                    sub_chunk = ""
                    for s in sentences:
                        if len(sub_chunk) + len(s) + 1 <= chunk_size:
                            sub_chunk = (sub_chunk + " " + s).strip() if sub_chunk else s
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = s
                    if sub_chunk:
                        current_chunk = sub_chunk
                else:
                    current_chunk = p

        if current_chunk:
            chunks.append(current_chunk)

        # Fallback if no paragraph chunking was produced
        if not chunks and text:
            step = chunk_size - overlap
            for i in range(0, len(text), max(1, step)):
                chunks.append(text[i:i + chunk_size])

        return [{"text": c, "page": page_num} for c in chunks if len(c.strip()) > 15]

    def index_document(self, filename: str, content: bytes) -> Dict[str, Any]:
        """
        Processes document, splits into chunks, saves in ChromaDB.
        Returns: { "doc_id": str, "filename": str, "chunks": int }
        """
        doc_id = str(uuid.uuid4())
        pages = self.extract_text_with_metadata(filename, content)
        
        if not pages:
            raise ValueError(f"No readable text could be extracted from {filename}.")

        all_chunks = []
        for p in pages:
            p_chunks = self.chunk_page_text(p["text"], page_num=p["page"])
            all_chunks.extend(p_chunks)

        if not all_chunks:
            # If everything was too short, wrap raw pages
            for p in pages:
                all_chunks.append({"text": p["text"], "page": p["page"]})

        # Prepare records for ChromaDB
        ids = []
        documents = []
        metadatas = []

        for idx, item in enumerate(all_chunks):
            chunk_id = f"{doc_id}_c{idx}"
            ids.append(chunk_id)
            documents.append(item["text"])
            metadatas.append({
                "doc_id": doc_id,
                "filename": filename,
                "page": int(item["page"]),
                "chunk_index": idx
            })

        # Add to ChromaDB
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )

        # Register in metadata store
        from datetime import datetime
        reg = self._get_registry()
        reg[doc_id] = {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(all_chunks),
            "pages_count": len(pages),
            "uploaded_at": datetime.utcnow().isoformat()
        }
        self._save_registry(reg)

        return {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(all_chunks)
        }

    def ask_document(self, doc_id: str, question: str) -> Dict[str, Any]:
        """
        Queries ChromaDB for top 4 chunks for the given doc_id,
        and generates an answer.
        Returns: { "answer": str, "sources": list[int] }
        """
        # Check if doc exists in collection
        total_chunks_resp = self.collection.get(where={"doc_id": doc_id}, limit=1)
        if not total_chunks_resp or not total_chunks_resp["ids"]:
            return {
                "answer": f"Document ID '{doc_id}' was not found in the vector database.",
                "sources": []
            }

        # Query top 4 chunks
        query_res = self.collection.query(
            query_texts=[question],
            n_results=4,
            where={"doc_id": doc_id}
        )

        doc_chunks = query_res.get("documents", [[]])[0]
        metadata_list = query_res.get("metadatas", [[]])[0]

        if not doc_chunks:
            return {
                "answer": "No relevant context found in this document for your question.",
                "sources": []
            }

        # Collect unique sorted source pages
        raw_pages = [int(meta["page"]) for meta in metadata_list if "page" in meta]
        sources: List[int] = sorted(list(set(raw_pages)))

        # Generate answer: try LLM first if configured, else extractive synthesis
        answer = self._generate_answer(question, doc_chunks, metadata_list)

        return {
            "answer": answer,
            "sources": sources
        }

    def _generate_answer(self, question: str, chunks: List[str], metadatas: List[Dict[str, Any]]) -> str:
        # Context block formatted with page indicators
        context_blocks = []
        for idx, (chunk, meta) in enumerate(zip(chunks, metadatas)):
            page_num = meta.get("page", 1)
            context_blocks.append(f"[Excerpt {idx+1} | Page {page_num}]:\n{chunk.strip()}")
        context_str = "\n\n".join(context_blocks)

        # 1. Try Gemini if GEMINI_API_KEY is set
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_api_key)
                prompt = (
                    f"You are an accurate, helpful assistant answering questions strictly based on the provided document excerpts.\n"
                    f"Always reference the relevant page numbers in your answer when citing facts.\n\n"
                    f"Context:\n{context_str}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer:"
                )
                for model_name in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"]:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt
                        )
                        if response and response.text:
                            return response.text.strip()
                    except Exception as model_err:
                        print(f"[RAGService] Gemini model {model_name} failed: {model_err}")
                        continue
            except Exception as e:
                print(f"[RAGService] Gemini generation failed, falling back: {e}")

        # 2. Try OpenAI if OPENAI_API_KEY is set
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_api_key)
                prompt = (
                    f"You are an accurate assistant answering questions strictly based on the provided document excerpts.\n"
                    f"Cite the relevant page numbers from the context in your answer.\n\n"
                    f"Context:\n{context_str}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer:"
                )
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                content = res.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as e:
                print(f"[RAGService] OpenAI generation failed, falling back: {e}")

        # 3. Built-in Local Semantic Synthesis Fallback (Runs 100% offline with zero external API keys!)
        return self._synthesize_extractive_answer(question, chunks, metadatas)

    def _synthesize_extractive_answer(self, question: str, chunks: List[str], metadatas: List[Dict[str, Any]]) -> str:
        """
        High-fidelity semantic synthesis from retrieved chunks with page citations.
        Extracts the most relevant statements matching the user's inquiry terms.
        """
        # Keyword tokenization from question
        q_words = set(re.findall(r"\w+", question.lower()))
        # Filter common stopwords
        stopwords = {"what", "is", "the", "a", "an", "and", "or", "in", "on", "of", "to", "for", "with", "how", "why", "who", "where", "can", "does", "do", "explain", "describe", "tell", "me", "about"}
        keywords = {w for w in q_words if w not in stopwords and len(w) > 2}

        ranked_sentences = []
        for chunk, meta in zip(chunks, metadatas):
            page_num = meta.get("page", 1)
            # Split chunk into sentences
            sentences = re.split(r"(?<=[.!?])\s+", chunk.replace("\n", " "))
            for sent in sentences:
                sent_clean = sent.strip()
                if len(sent_clean) < 20:
                    continue
                sent_words = set(re.findall(r"\w+", sent_clean.lower()))
                overlap = len(keywords.intersection(sent_words))
                if overlap > 0:
                    ranked_sentences.append({
                        "sentence": sent_clean,
                        "page": page_num,
                        "score": overlap,
                        "len": len(sent_clean)
                    })

        # Sort by relevance score
        ranked_sentences.sort(key=lambda s: (-s["score"], s["len"]))

        if not ranked_sentences:
            # If no direct keyword overlap, summarize top chunk directly
            top_chunk = chunks[0].strip()
            top_page = metadatas[0].get("page", 1)
            first_few_lines = " ".join([line.strip() for line in top_chunk.split("\n")[:4] if line.strip()])
            return (
                f"Based on the most relevant excerpt retrieved from **Page {top_page}**:\n\n"
                f"> \"{first_few_lines}\"\n\n"
                f"The document discusses this topic on **Page {top_page}**. Please refer to the cited page for full context."
            )

        # Select top unique sentences
        selected = []
        seen = set()
        pages_cited = set()
        for item in ranked_sentences:
            s_text = item["sentence"]
            if s_text not in seen:
                seen.add(s_text)
                selected.append(item)
                pages_cited.add(item["page"])
                if len(selected) >= 3:
                    break

        # Compose coherent response
        bullet_points = "\n".join([f"- **(Page {item['page']})**: \"{item['sentence']}\"" for item in selected])
        pages_str = ", ".join(f"Page {p}" for p in sorted(list(pages_cited)))
        
        answer = (
            f"According to the document ({pages_str}), the following key points address your query:\n\n"
            f"{bullet_points}\n\n"
            f"*Context retrieved from top 4 semantic chunks in ChromaDB.*"
        )
        return answer
