import os
import re
import json
import uuid
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import pymupdf as fitz  # PyMuPDF
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
        self.files_dir = self.persist_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)

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
                if legacy_col.count() == 0:
                    return
                old_data = legacy_col.get()
                if old_data and old_data.get("ids"):
                    target_existing = set(self.collection.get(include=[]).get("ids", []))
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
                self._all_docs_questions_cache = None
                self._all_docs_questions_cache_key = None
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

    def index_document(self, filename: str, content: Union[bytes, str], llm_service=None, firebase_service=None) -> Dict[str, Any]:
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

        # Update local registry
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
        self._all_docs_questions_cache = None
        self._all_docs_questions_cache_key = None

        # Cache raw file and page structures locally for instant page viewing
        try:
            content_bytes = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8")
            file_save_path = self.files_dir / f"{doc_id}_{filename}"
            with open(file_save_path, "wb") as f:
                f.write(content_bytes)

            pages_save_path = self.files_dir / f"{doc_id}_pages.json"
            with open(pages_save_path, "w", encoding="utf-8") as f:
                json.dump(pages, f, ensure_ascii=False, indent=2)
        except Exception as f_err:
            print(f"[VectorStore] Notice caching raw file / pages: {f_err}")

        # Synchronize with Firebase Firestore & Storage if active
        if firebase_service and getattr(firebase_service, "is_active", False):
            try:
                storage_url = None
                content_bytes = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8")
                storage_url = firebase_service.upload_file(doc_id, filename, content_bytes)
                firebase_service.save_document(
                    doc_id=doc_id,
                    filename=filename,
                    chunks=len(documents),
                    pages_count=len(pages),
                    suggested_questions=suggested_questions,
                    storage_url=storage_url
                )
            except Exception as fe:
                print(f"[VectorStore] Notice syncing document to Firebase: {fe}")

        return {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(documents),
            "pages_count": len(pages),
            "suggested_questions": suggested_questions
        }

    def get_suggested_questions(self, doc_id: str, llm_service=None) -> List[str]:
        """
        Retrieves or dynamically generates 3-5 variable suggested questions suitable for this document or all documents.
        When doc_id is 'all' (main page), it reads across all uploaded files to generate relevant questions for each file.
        """
        is_all = not doc_id or str(doc_id).strip().lower() in ("all", "*", "")
        reg = self._get_registry()

        if is_all:
            if not reg:
                return [
                    "How do I upload and index documents in this system?",
                    "What file formats (PDF, DOCX, TXT) are supported?"
                ]

            # Invalidate/check multi-document suggestions cache
            current_cache_key = tuple(sorted(reg.keys()))
            if getattr(self, "_all_docs_questions_cache_key", None) == current_cache_key:
                cached_questions = getattr(self, "_all_docs_questions_cache", None)
                if cached_questions and len(cached_questions) >= 2:
                    return cached_questions

            # Read excerpts across ALL uploaded files
            all_files_data = []
            for d_id, doc_info in reg.items():
                fn = doc_info.get("filename", "document")
                chunks = []
                try:
                    res = self.collection.get(where={"doc_id": d_id}, limit=2)
                    if res and res.get("documents"):
                        chunks = res["documents"]
                except Exception:
                    pass

                if not chunks:
                    pages = self.get_all_pages_for_document(d_id)
                    if pages:
                        chunks = [p["text"][:600] for p in pages[:2]]

                all_files_data.append({
                    "doc_id": d_id,
                    "filename": fn,
                    "chunks": chunks
                })

            questions = []
            if llm_service is not None and hasattr(llm_service, "generate_all_documents_suggested_questions"):
                try:
                    questions = llm_service.generate_all_documents_suggested_questions(all_files_data)
                except Exception as e:
                    print(f"[VectorStore] Error generating multi-document questions: {e}")

            if not questions:
                # Heuristic fallback across all files
                for d in all_files_data:
                    base_fn = re.sub(r"\.[a-zA-Z0-9]+$", "", d["filename"])
                    questions.append(f"What key information or problems are covered in {base_fn}?")
                if len(all_files_data) > 1:
                    questions.append("What are the primary findings and common themes across all uploaded files?")

            # Cache the generated questions
            self._all_docs_questions_cache_key = current_cache_key
            self._all_docs_questions_cache = questions[:6]
            return self._all_docs_questions_cache

        else:
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

    def get_all_pages_for_document(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Returns full text for every page of the document: [{'page': 1, 'text': '...'}, ...]
        Uses local cache file if available, or reconstructs ordered page text from ChromaDB chunks.
        """
        pages_json = self.files_dir / f"{doc_id}_pages.json"
        if pages_json.exists():
            try:
                with open(pages_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass

        matching = self.collection.get(where={"doc_id": doc_id})
        if not matching or not matching.get("documents"):
            try:
                col_names = [c.name for c in self.client.list_collections()]
                if "task_rag_documents" in col_names:
                    legacy_col = self.client.get_collection("task_rag_documents")
                    matching = legacy_col.get(where={"doc_id": doc_id})
            except Exception:
                pass

        if not matching or not matching.get("documents"):
            return []

        page_chunks: Dict[int, List[Tuple[int, str]]] = {}
        for doc, meta in zip(matching["documents"], matching["metadatas"]):
            p_num = int(meta.get("page", 1))
            c_idx = int(meta.get("chunk_index", 0))
            clean_doc = re.sub(r"^\[Page\s+\d+\]\s*", "", doc).strip()
            if p_num not in page_chunks:
                page_chunks[p_num] = []
            page_chunks[p_num].append((c_idx, clean_doc))

        sorted_pages = []
        for p_num in sorted(page_chunks.keys()):
            chunks = sorted(page_chunks[p_num], key=lambda x: x[0])
            full_page_text = "\n\n".join([c[1] for c in chunks])
            sorted_pages.append({"page": p_num, "text": full_page_text})

        try:
            with open(self.files_dir / f"{doc_id}_pages.json", "w", encoding="utf-8") as f:
                json.dump(sorted_pages, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return sorted_pages

    def _reconstruct_document_file(self, doc_id: str, doc_info: Dict[str, Any]) -> Optional[Path]:
        """
        For pre-existing documents indexed without raw file on disk,
        synthesizes a clean viewable document (PDF for .pdf, text for .txt/.docx).
        """
        filename = doc_info.get("filename", f"{doc_id}.pdf")
        ext = filename.lower().split(".")[-1]
        target_path = self.files_dir / f"{doc_id}_{filename}"
        if target_path.exists():
            return target_path

        pages_data = self.get_all_pages_for_document(doc_id)
        if not pages_data:
            return None

        try:
            if ext == "pdf":
                doc = fitz.open()
                max_page = max((p["page"] for p in pages_data), default=len(pages_data))
                pages_by_num = {p["page"]: p for p in pages_data}

                for p_num in range(1, max_page + 1):
                    page = doc.new_page(width=595, height=842)
                    header_text = f"{filename}  •  Page {p_num} of {max_page}"
                    page.insert_text(
                        fitz.Point(40, 36),
                        header_text,
                        fontsize=9,
                        fontname="helv",
                        color=(0.3, 0.3, 0.4)
                    )
                    page.draw_line(fitz.Point(40, 42), fitz.Point(555, 42), color=(0.75, 0.75, 0.8), width=0.7)

                    p = pages_by_num.get(p_num)
                    if p and p.get("text"):
                        rect = fitz.Rect(40, 56, 555, 800)
                        page.insert_textbox(rect, p["text"], fontsize=10, fontname="helv", color=(0.1, 0.1, 0.15))

                doc.save(str(target_path))
                doc.close()
                return target_path
            else:
                full_text = f"Document: {filename}\nTotal Pages: {len(pages_data)}\n\n" + "\n\n".join(
                    [f"=== [ Page {p['page']} ] ===\n\n{p['text']}" for p in pages_data]
                )
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(full_text)
                return target_path
        except Exception as e:
            print(f"[VectorStore] Error reconstructing document file: {e}")
            return None

    def get_document_file_path(self, doc_id: str) -> Optional[Path]:
        """
        Returns the absolute Path of the stored file, or reconstructs it if needed.
        """
        reg = self._get_registry()
        doc_info = reg.get(doc_id, {})
        filename = doc_info.get("filename")

        if filename:
            p = self.files_dir / f"{doc_id}_{filename}"
            if p.exists():
                return p

        for f in self.files_dir.glob(f"{doc_id}_*"):
            if not f.name.endswith("_pages.json"):
                return f

        return self._reconstruct_document_file(doc_id, doc_info)

    def get_document_page(self, doc_id: str, page_num: int) -> Dict[str, Any]:
        """
        Retrieves page details: total pages, page text content, file metadata, and view link.
        """
        reg = self._get_registry()
        doc_info = reg.get(doc_id, {})
        filename = doc_info.get("filename", "document")
        ext = filename.lower().split(".")[-1]

        all_pages = self.get_all_pages_for_document(doc_id)
        total_pages = doc_info.get("pages_count") or (len(all_pages) if all_pages else 1)

        target_page = next((p for p in all_pages if p["page"] == page_num), None)
        content = target_page["text"] if target_page else ""

        file_path = self.get_document_file_path(doc_id)
        has_raw = file_path is not None and file_path.exists()

        pdf_url = f"http://localhost:8000/api/documents/{doc_id}/file#page={page_num}"
        file_url = pdf_url if ext == "pdf" else f"http://localhost:8000/api/documents/{doc_id}/file"

        return {
            "doc_id": doc_id,
            "filename": filename,
            "page": page_num,
            "total_pages": total_pages,
            "content": content,
            "file_type": ext,
            "has_raw_file": has_raw,
            "file_url": file_url
        }

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

    def retrieve_top_chunks(self, doc_id: Optional[str], question: str, n_results: int = 4) -> Tuple[List[str], List[Dict[str, Any]], List[int]]:
        """
        High-Accuracy Hybrid Retrieval:
        1. Retrieves candidate chunks using dense ChromaDB vector search across a specific document or all uploaded documents.
        2. Ranks candidates using Reciprocal Rank Fusion (RRF) combining vector distance and lexical score.
        3. Suppresses near-duplicate chunks for diverse and complete context.
        4. Returns the top 4 most accurate chunks with source page numbers.
        """
        is_all_docs = not doc_id or str(doc_id).strip().lower() in ("all", "*", "")

        total_chunks = self.collection.count()
        if total_chunks == 0:
            return [], [], []

        candidate_k = min(32, total_chunks)
        cand_chunks: List[str] = []
        cand_metas: List[Dict[str, Any]] = []
        cand_distances: List[float] = []

        try:
            query_kwargs = {
                "query_texts": [question],
                "n_results": candidate_k
            }
            if not is_all_docs:
                query_kwargs["where"] = {"doc_id": doc_id}

            query_res = self.collection.query(**query_kwargs)
            cand_chunks = query_res.get("documents", [[]])[0]
            cand_metas = query_res.get("metadatas", [[]])[0]
            cand_distances = query_res.get("distances", [[]])[0] if "distances" in query_res and query_res["distances"] else []
        except Exception as query_err:
            print(f"[VectorStore] Dense query fallback notice: {query_err}")

        # Fallback if query returned empty but document has chunks
        if not cand_chunks and not is_all_docs:
            try:
                fb = self.collection.get(where={"doc_id": doc_id}, limit=candidate_k)
                if fb and fb.get("documents"):
                    cand_chunks = fb["documents"]
                    cand_metas = fb.get("metadatas", [])
                    cand_distances = []
            except Exception:
                pass

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
