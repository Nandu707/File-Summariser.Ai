import os
import re
import json
import uuid
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import fitz  # PyMuPDF
import chromadb
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# Vector DB path: ./vector_db (defaults to persistent local ChromaDB storage)
DEFAULT_VECTOR_DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "vector_db"
VECTOR_DB_DIR = Path(os.getenv("CHROMA_PERSIST_DIRECTORY", str(DEFAULT_VECTOR_DB_DIR)))


class VectorStoreService:
    def __init__(self, persist_dir: Optional[str] = None):
        # Resolve paths relative to the source file location for consistency
        # regardless of the current working directory when the server starts
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        backend_root = Path(__file__).resolve().parent.parent.parent
        root_vdb = project_root / "vector_db"
        backend_vdb = backend_root / "vector_db"

        if persist_dir:
            self.persist_dir = Path(persist_dir).resolve()
        else:
            # Always prefer the project root vector_db since that's where
            # documents are indexed. This avoids the CWD-dependent bug where
            # "./vector_db" in .env resolves to different directories depending
            # on where uvicorn is launched from.
            if root_vdb.exists() and (root_vdb / "chroma.sqlite3").exists():
                self.persist_dir = root_vdb.resolve()
            elif backend_vdb.exists() and (backend_vdb / "chroma.sqlite3").exists():
                self.persist_dir = backend_vdb.resolve()
            elif os.getenv("CHROMA_PERSIST_DIRECTORY"):
                env_dir = Path(os.getenv("CHROMA_PERSIST_DIRECTORY"))
                if env_dir.is_absolute():
                    self.persist_dir = env_dir.resolve()
                else:
                    self.persist_dir = (project_root / env_dir).resolve()
            else:
                self.persist_dir = root_vdb.resolve()

        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize persistent local ChromaDB client
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name="task_rag_vector_store",
            metadata={"description": "High-accuracy chunks split by RecursiveCharacterTextSplitter"}
        )

        # High-accuracy sentence-aware text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]
        )

        self._ensure_registry()
        self._sync_legacy_collections()

    def _sync_legacy_collections(self):
        """Auto-migrates any chunks stored in legacy task_rag_documents collection."""
        try:
            col_names = [c.name for c in self.client.list_collections()]
            if "task_rag_documents" in col_names:
                legacy_col = self.client.get_collection("task_rag_documents")
                old_data = legacy_col.get()
                if old_data and old_data.get("ids"):
                    target_existing = set(self.collection.get().get("ids", []))
                    new_ids = []
                    new_docs = []
                    new_metas = []
                    for cid, doc, meta in zip(old_data["ids"], old_data["documents"], old_data["metadatas"]):
                        if cid not in target_existing:
                            new_ids.append(cid)
                            new_docs.append(doc)
                            new_metas.append(meta)
                    if new_ids:
                        for i in range(0, len(new_ids), 100):
                            self.collection.add(
                                ids=new_ids[i:i + 100],
                                documents=new_docs[i:i + 100],
                                metadatas=new_metas[i:i + 100]
                            )
        except Exception as e:
            print(f"[VectorStore] Legacy collection sync notice: {e}")

    def _ensure_registry(self):
        try:
            reg_file = self.persist_dir / "documents_registry.json"
            if not reg_file.exists():
                with open(reg_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)
        except Exception as e:
            print(f"[VectorStore] Warning creating registry file: {e}")

    def _get_registry(self) -> Dict[str, Any]:
        reg_file = self.persist_dir / "documents_registry.json"
        if reg_file.exists():
            try:
                with open(reg_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_registry(self, registry: Dict[str, Any]):
        try:
            reg_file = self.persist_dir / "documents_registry.json"
            with open(reg_file, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
        except Exception as e:
            print(f"[VectorStore] Error saving document registry: {e}")

    def list_documents(self) -> List[Dict[str, Any]]:
        reg = self._get_registry()
        docs = list(reg.values())
        docs.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
        return docs

    def delete_document(self, doc_id: str) -> bool:
        try:
            try:
                self.collection.delete(where={"doc_id": doc_id})
            except Exception:
                pass
            try:
                col_names = [c.name for c in self.client.list_collections()]
                if "task_rag_documents" in col_names:
                    legacy_col = self.client.get_collection("task_rag_documents")
                    legacy_col.delete(where={"doc_id": doc_id})
            except Exception:
                pass
            reg = self._get_registry()
            if doc_id in reg:
                del reg[doc_id]
                self._save_registry(reg)
            return True
        except Exception as e:
            print(f"[VectorStore] Error deleting document {doc_id}: {e}")
            return False

    def _clean_text(self, text: str) -> str:
        """Cleans and normalizes text for high-accuracy embedding and retrieval."""
        if not text:
            return ""
        # Remove null bytes and non-printable control characters
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
        # De-hyphenate broken words across line breaks (e.g. "superposi-\ntion" -> "superposition")
        text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
        # Normalize whitespace while preserving paragraph structure
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def extract_text_with_page_metadata(self, filename: str, content: Union[bytes, str]) -> List[Dict[str, Any]]:
        """
        Extracts text with page metadata.
        Uses PyMuPDF (fitz) for PDF files in visual reading order (sort=True) for large multi-page files.
        Cleans repetitive running headers/footers to avoid embedding contamination.
        """
        ext = filename.lower().split(".")[-1]
        pages_data = []

        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        if ext == "pdf":
            # PyMuPDF with sort=True preserves column & block reading order across large PDFs
            with fitz.open(stream=content_bytes, filetype="pdf") as doc:
                total_pages = len(doc)
                raw_pages = []
                for page_idx in range(total_pages):
                    page = doc[page_idx]
                    raw_text = page.get_text("text", sort=True) or ""
                    cleaned = self._clean_text(raw_text)
                    raw_pages.append(cleaned)

                # For multi-page PDFs (3+ pages), detect repeating running headers or footers
                lines_by_page = [[ln.strip() for ln in p.split("\n") if ln.strip()] for p in raw_pages]
                first_lines = [lines[0] for lines in lines_by_page if lines]
                last_lines = [lines[-1] for lines in lines_by_page if lines]

                common_header = None
                common_footer = None
                if total_pages >= 3:
                    from collections import Counter
                    h_counts = Counter(first_lines)
                    f_counts = Counter(last_lines)
                    if h_counts and h_counts.most_common(1)[0][1] >= (total_pages * 0.75):
                        common_header = h_counts.most_common(1)[0][0]
                    if f_counts and f_counts.most_common(1)[0][1] >= (total_pages * 0.75):
                        common_footer = f_counts.most_common(1)[0][0]

                for page_idx, raw_p in enumerate(raw_pages):
                    if not raw_p:
                        continue
                    lines = [ln.strip() for ln in raw_p.split("\n") if ln.strip()]
                    if common_header and lines and lines[0] == common_header:
                        lines = lines[1:]
                    if common_footer and lines and lines[-1] == common_footer:
                        lines = lines[:-1]

                    final_page_text = "\n".join(lines).strip()
                    if final_page_text:
                        pages_data.append({
                            "page": page_idx + 1,
                            "text": final_page_text
                        })
        elif ext in ["txt", "md"]:
            raw_text = content_bytes.decode("utf-8", errors="replace")
            cleaned_full = self._clean_text(raw_text)

            # Check for explicit section/page indicators in text
            page_pattern = re.compile(
                r"(?:^|\n)(?:#+\s*)?(?:Section\s+\d+.*?)?\(?(?:Page|p\.)\s*(\d+)\)?:?", 
                re.IGNORECASE
            )
            matches = list(page_pattern.finditer(cleaned_full))

            if len(matches) > 1:
                # Split along explicit page headings
                for i in range(len(matches)):
                    start = matches[i].start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned_full)
                    page_num = int(matches[i].group(1))
                    seg_text = cleaned_full[start:end].strip()
                    if seg_text:
                        pages_data.append({"page": page_num, "text": seg_text})
            elif "\x0c" in raw_text:
                # Form-feed page breaks
                for idx, p in enumerate(raw_text.split("\x0c")):
                    cl = self._clean_text(p)
                    if cl:
                        pages_data.append({"page": idx + 1, "text": cl})
            elif len(cleaned_full) > 3000:
                # Segment large text into logical pages (~2500 chars)
                virtual_pages = [cleaned_full[i:i + 2500] for i in range(0, len(cleaned_full), 2500)]
                for idx, vp in enumerate(virtual_pages):
                    cl = self._clean_text(vp)
                    if cl:
                        pages_data.append({"page": idx + 1, "text": cl})
            else:
                pages_data.append({"page": 1, "text": cleaned_full})
        elif ext in ["docx", "doc"]:
            # Microsoft Word document extraction (.docx / .doc)
            raw_blocks = []
            try:
                import io
                import docx
                doc = docx.Document(io.BytesIO(content_bytes))
                for p in doc.paragraphs:
                    t = p.text.strip()
                    if t:
                        raw_blocks.append(t)
                for tbl in doc.tables:
                    for row in tbl.rows:
                        row_t = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                        if row_t:
                            raw_blocks.append(row_t)
            except Exception as docx_err:
                print(f"[VectorStore] python-docx parsing failed, falling back to stream extraction: {docx_err}")
                text = content_bytes.decode("latin-1", errors="ignore")
                clean = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
                clean = re.sub(r" {2,}", " ", clean).strip()
                raw_blocks = [clean] if clean else []

            full_text = "\n\n".join(raw_blocks)
            cleaned_full = self._clean_text(full_text)

            if not cleaned_full:
                raise ValueError(f"Could not extract any readable text from {filename}.")

            # Split into logical pages (~2000 characters) to provide accurate page-level citations
            page_size = 2000
            if len(cleaned_full) > page_size:
                virtual_pages = [cleaned_full[i:i + page_size] for i in range(0, len(cleaned_full), page_size)]
                for idx, vp in enumerate(virtual_pages):
                    cl = self._clean_text(vp)
                    if cl:
                        pages_data.append({"page": idx + 1, "text": cl})
            else:
                pages_data.append({"page": 1, "text": cleaned_full})
        else:
            raise ValueError(f"Unsupported file format: .{ext}. Supported formats are .pdf, .txt, .docx, and .doc.")

        return pages_data

    def index_document(self, filename: str, content: Union[bytes, str], llm_service=None) -> Dict[str, Any]:
        """
        Extracts text, splits using RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200),
        generates embeddings and stores in persistent ChromaDB client with doc_id and page metadata.
        Optimized for large files with batched insertions.
        Returns: { "doc_id": str, "filename": str, "chunks": int, "suggested_questions": list[str] }
        """
        doc_id = str(uuid.uuid4())
        pages = self.extract_text_with_page_metadata(filename, content)

        if not pages:
            raise ValueError(f"No extractable text found in '{filename}'.")

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        chunk_counter = 0

        for page_data in pages:
            page_num = int(page_data["page"])
            page_text = page_data["text"]

            # Split text using RecursiveCharacterTextSplitter (chunk_size=1000, chunk_overlap=200)
            page_chunks = self.text_splitter.split_text(page_text)

            for chunk_str in page_chunks:
                clean_chunk = chunk_str.strip()
                if not clean_chunk or len(clean_chunk) < 10:
                    continue

                chunk_id = f"{doc_id}_c{chunk_counter}"
                ids.append(chunk_id)
                # Store chunk with unambiguous page contextual marker
                documents.append(f"[Page {page_num}] {clean_chunk}")
                metadatas.append({
                    "doc_id": doc_id,
                    "page": page_num,
                    "filename": filename,
                    "chunk_index": chunk_counter
                })
                chunk_counter += 1

        if not ids:
            for p in pages:
                chunk_id = f"{doc_id}_c{chunk_counter}"
                ids.append(chunk_id)
                documents.append(f"[Page {p['page']}] {p['text']}")
                metadatas.append({
                    "doc_id": doc_id,
                    "page": int(p["page"]),
                    "filename": filename,
                    "chunk_index": chunk_counter
                })
                chunk_counter += 1

        # Store in persistent ChromaDB collection in safe batches of 200 for fast memory & CPU efficiency
        batch_size = 200
        for i in range(0, len(ids), batch_size):
            self.collection.add(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size]
            )

        # Generate document-tailored suggested questions
        suggested_questions: List[str] = []
        if llm_service is not None:
            sample_chunks = [d for d in documents[:3]]
            try:
                suggested_questions = llm_service.generate_suggested_questions(filename, sample_chunks)
            except Exception as e:
                print(f"[VectorStore] Notice generating suggested questions: {e}")

        # Update registry
        from datetime import datetime
        reg = self._get_registry()
        reg[doc_id] = {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(documents),
            "pages_count": len(pages),
            "uploaded_at": datetime.utcnow().isoformat(),
            "suggested_questions": suggested_questions
        }
        self._save_registry(reg)

        return {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(documents),
            "suggested_questions": suggested_questions
        }

    def get_suggested_questions(self, doc_id: str, llm_service=None) -> List[str]:
        """
        Retrieves or dynamically generates 3-4 variable suggested questions suitable for this document.
        """
        reg = self._get_registry()
        doc = reg.get(doc_id)
        if doc and doc.get("suggested_questions") and len(doc["suggested_questions"]) >= 2:
            return doc["suggested_questions"]

        filename = doc.get("filename", "document") if doc else "document"
        
        # Retrieve sample chunks from collection for this document
        sample_chunks = []
        try:
            res = self.collection.get(where={"doc_id": doc_id}, limit=3)
            if res and res.get("documents"):
                sample_chunks = res["documents"]
        except Exception as e:
            print(f"[VectorStore] Notice getting chunks for suggestions: {e}")

        questions = []
        if llm_service is not None:
            try:
                questions = llm_service.generate_suggested_questions(filename, sample_chunks)
            except Exception as e:
                print(f"[VectorStore] Error generating questions: {e}")

        if not questions:
            questions = [
                f"What is the central topic and summary of {filename}?",
                "What key numbers, statistics, or metrics are mentioned?",
                "What are the primary conclusions or next steps?"
            ]

        # Cache in registry if document exists
        if doc:
            doc["suggested_questions"] = questions
            reg[doc_id] = doc
            self._save_registry(reg)

        return questions

    def _compute_keyword_score(self, query: str, text: str) -> float:
        """
        Computes BM25-inspired lexical relevance score between question and candidate text chunk.
        Weights exact numbers, percentages, acronyms, and query coverage heavily.
        """
        text_lower = text.lower()
        query_lower = query.lower()

        # Extract keywords and specific entities
        stopwords = {
            "what", "is", "the", "a", "an", "and", "or", "in", "on", "of", "to", "for", 
            "with", "how", "why", "who", "where", "can", "does", "do", "explain", "describe", 
            "tell", "me", "about", "are", "by", "from", "at", "as", "which", "will", "would",
            "should", "could", "been", "have", "has", "had", "this", "that", "these", "those"
        }
        tokens = re.findall(r"\b\w+\b", query_lower)
        keywords = [t for t in tokens if t not in stopwords and len(t) > 1]

        if not keywords:
            return 0.0

        score = 0.0

        # 1. Exact phrase matches (highest reward)
        if len(query_lower) > 10 and query_lower in text_lower:
            score += 6.0

        # 2. Key terms match + coverage calculation
        matched_keywords = 0
        for kw in set(keywords):
            count = len(re.findall(r"\b" + re.escape(kw) + r"\b", text_lower))
            if count > 0:
                matched_keywords += 1
                score += 1.2 + math.log(1 + count)

        # Query coverage reward: what fraction of the question's keywords are in this chunk?
        coverage = matched_keywords / len(set(keywords))
        score += (coverage * 4.0)

        # 3. Numbers, percentages, dates in query (critical for factual RAG accuracy)
        numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", query)
        for num in numbers:
            if num.lower() in text_lower:
                score += 3.5

        # 4. Acronyms & capitalized terms (e.g. RAG, VQE, QAOA, NISQ, PyMuPDF, ChromaDB)
        acronyms = re.findall(r"\b[A-Z]{2,}\b", query)
        for acr in acronyms:
            if acr in text:
                score += 3.0

        return score

    def retrieve_top_chunks(self, doc_id: str, question: str, n_results: int = 4) -> Tuple[List[str], List[Dict[str, Any]], List[int]]:
        """
        High-Accuracy Hybrid Retrieval:
        1. Retrieves candidate chunks using dense ChromaDB vector search.
        2. Ranks candidates using Reciprocal Rank Fusion (RRF) combining vector distance and lexical score.
        3. Suppresses near-duplicate chunks for diverse and complete context.
        4. Returns the top 4 most accurate chunks with source page numbers.
        """
        matching = self.collection.get(where={"doc_id": doc_id})
        target_col = self.collection
        if not matching or not matching["ids"]:
            try:
                col_names = [c.name for c in self.client.list_collections()]
                if "task_rag_documents" in col_names:
                    legacy_col = self.client.get_collection("task_rag_documents")
                    legacy_match = legacy_col.get(where={"doc_id": doc_id})
                    if legacy_match and legacy_match["ids"]:
                        matching = legacy_match
                        target_col = legacy_col
            except Exception:
                pass

        if not matching or not matching["ids"]:
            return [], [], []

        doc_chunk_count = len(matching["ids"])

        # Fetch candidate pool (up to 32 chunks or all document chunks if fewer)
        candidate_k = min(32, doc_chunk_count)

        try:
            query_res = target_col.query(
                query_texts=[question],
                n_results=candidate_k,
                where={"doc_id": doc_id}
            )
            cand_chunks: List[str] = query_res.get("documents", [[]])[0]
            cand_metas: List[Dict[str, Any]] = query_res.get("metadatas", [[]])[0]
            cand_distances: List[float] = query_res.get("distances", [[]])[0] if "distances" in query_res and query_res["distances"] else []
        except Exception as query_err:
            print(f"[VectorStore] Dense query fallback notice: {query_err}")
            cand_chunks = []
            cand_metas = []
            cand_distances = []

        # If vector query didn't return candidates but document has chunks, use all document chunks
        if not cand_chunks and matching and matching.get("documents"):
            cand_chunks = matching["documents"][:candidate_k]
            cand_metas = matching.get("metadatas", [])[:candidate_k] if matching.get("metadatas") else []
            cand_distances = []

        if not cand_chunks:
            return [], [], []

        # If document has <= n_results chunks, return directly
        if len(cand_chunks) <= n_results:
            final_chunks = cand_chunks
            final_metas = cand_metas
        else:
            # Hybrid Re-ranking: Combine Vector Rank and Lexical Relevance
            scored_candidates = []
            for rank_idx, (chunk, meta) in enumerate(zip(cand_chunks, cand_metas)):
                # RRF Vector Score: 1 / (60 + rank)
                rrf_vector = 1.0 / (60.0 + (rank_idx + 1))

                # Distance score (if Chroma returned cosine distance: smaller distance = more similar)
                if cand_distances and rank_idx < len(cand_distances):
                    dist = cand_distances[rank_idx]
                    sim = max(0.0, 1.0 - dist)
                else:
                    sim = 1.0 / (1.0 + rank_idx)

                # Lexical keyword score
                kw_score = self._compute_keyword_score(question, chunk)

                # Combined Hybrid Score
                total_score = (rrf_vector * 100.0) + (sim * 10.0) + (kw_score * 5.0)

                scored_candidates.append({
                    "chunk": chunk,
                    "meta": meta,
                    "score": total_score
                })

            # Sort by total score descending
            scored_candidates.sort(key=lambda x: x["score"], reverse=True)

            # Deduplication: suppress near-duplicates (>75% token overlap) to ensure rich context
            selected_candidates = []
            selected_tokens_list = []

            for cand in scored_candidates:
                cand_tokens = set(re.findall(r"\w+", cand["chunk"].lower()))
                is_duplicate = False
                for prev_tokens in selected_tokens_list:
                    intersection = len(cand_tokens.intersection(prev_tokens))
                    union = len(cand_tokens.union(prev_tokens))
                    if union > 0 and (intersection / union) > 0.75:
                        is_duplicate = True
                        break

                if not is_duplicate or len(selected_candidates) + (len(scored_candidates) - scored_candidates.index(cand)) <= n_results:
                    selected_candidates.append(cand)
                    selected_tokens_list.append(cand_tokens)

                if len(selected_candidates) == n_results:
                    break

            # If deduplication was too aggressive, fill up to n_results
            if len(selected_candidates) < n_results:
                for cand in scored_candidates:
                    if cand not in selected_candidates:
                        selected_candidates.append(cand)
                        if len(selected_candidates) == n_results:
                            break

            final_chunks = [c["chunk"] for c in selected_candidates]
            final_metas = [c["meta"] for c in selected_candidates]

        # Extract sorted unique page numbers: list[int]
        raw_pages = []
        for m in final_metas:
            if isinstance(m, dict) and "page" in m:
                try:
                    raw_pages.append(int(m["page"]))
                except (ValueError, TypeError):
                    pass
        sources: List[int] = sorted(list(set(raw_pages)))

        return final_chunks, final_metas, sources


# Alias for VectorStoreService
VectorStore = VectorStoreService

# Default singleton instance
_default_vector_store = None

def get_vector_store(persist_dir: Optional[str] = None) -> VectorStoreService:
    global _default_vector_store
    if _default_vector_store is None or persist_dir is not None:
        _default_vector_store = VectorStoreService(persist_dir=persist_dir)
    return _default_vector_store

def index_document(filename: str, content: Union[bytes, str], persist_dir: Optional[str] = None) -> Dict[str, Any]:
    return get_vector_store(persist_dir).index_document(filename, content)

def retrieve_top_chunks(doc_id: str, question: str, n_results: int = 4, persist_dir: Optional[str] = None) -> Tuple[List[str], List[Dict[str, Any]], List[int]]:
    return get_vector_store(persist_dir).retrieve_top_chunks(doc_id, question, n_results=n_results)
