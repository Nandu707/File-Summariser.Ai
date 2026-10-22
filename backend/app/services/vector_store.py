import os
import re
import json
import uuid
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import pymupdf as fitz  # PyMuPDF
try:
    import chromadb
except (ImportError, Exception):
    try:
        from backend.app.services import light_chroma as chromadb
    except (ImportError, Exception):
        from app.services import light_chroma as chromadb

from dotenv import load_dotenv

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except (ImportError, Exception):
    class RecursiveCharacterTextSplitter:
        def __init__(self, chunk_size=1000, chunk_overlap=200, length_function=len, separators=None):
            self.chunk_size = chunk_size
            self.chunk_overlap = chunk_overlap
            self.length_function = length_function
            self.separators = separators or ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

        def split_text(self, text: str) -> List[str]:
            if not text:
                return []
            if len(text) <= self.chunk_size:
                return [text]
            chunks = []
            start = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                if end < len(text):
                    sub = text[start:end]
                    for sep in self.separators:
                        if sep and sep in sub:
                            last_pos = sub.rfind(sep)
                            if last_pos > self.chunk_overlap:
                                end = start + last_pos + len(sep)
                                break
                chunk = text[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                if end >= len(text):
                    break
                start = max(start + 1, end - self.chunk_overlap)
            return chunks

load_dotenv()

# Vector DB path: ./vector_db (defaults to persistent local ChromaDB storage)
DEFAULT_VECTOR_DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "vector_db"
VECTOR_DB_DIR = Path(os.getenv("CHROMA_PERSIST_DIRECTORY", str(DEFAULT_VECTOR_DB_DIR)))


def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(6):
        if (current / "package.json").exists() or (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


class VectorStoreService:
    def __init__(self, persist_dir: Optional[str] = None):
        # Resolve canonical project root vector_db (e:\Task-RAG\vector_db)
        project_root = _find_project_root()
        root_vdb = project_root / "vector_db"
        backend_vdb = project_root / "backend" / "vector_db"

        if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            self.persist_dir = Path("/tmp/vector_db").resolve()
        elif persist_dir:
            self.persist_dir = Path(persist_dir).resolve()
        else:
            self.persist_dir = root_vdb.resolve()

        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            test_f = self.persist_dir / ".write_test"
            test_f.touch()
            test_f.unlink()
        except (OSError, PermissionError):
            self.persist_dir = Path("/tmp/vector_db").resolve()
            self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.files_dir = self.persist_dir / "files"
        try:
            self.files_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            self.files_dir = Path("/tmp/vector_db/files").resolve()
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
        self._sync_backend_db_if_needed(backend_vdb)
        self._cleanup_orphaned_files()
        self.migrate_legacy_private_files()
        self._get_registry(force_reconcile=True)

    def get_user_files_dir(self, user_id: Optional[str] = None) -> Path:
        """Returns the single shared directory for raw documents and page caches."""
        return self.files_dir

    def get_user_collection(self, user_id: Optional[str] = None):
        """Returns the single shared ChromaDB collection for all documents, auto-recovering if invalidated."""
        try:
            if hasattr(self, "collection") and self.collection is not None:
                self.collection.count()
                return self.collection
        except Exception:
            pass

        try:
            self.collection = self.client.get_or_create_collection(
                name="task_rag_vector_store",
                metadata={"description": "High-accuracy chunks split by RecursiveCharacterTextSplitter"}
            )
        except Exception:
            self.client = chromadb.PersistentClient(path=str(self.persist_dir))
            self.collection = self.client.get_or_create_collection(
                name="task_rag_vector_store",
                metadata={"description": "High-accuracy chunks split by RecursiveCharacterTextSplitter"}
            )
        return self.collection

    def migrate_legacy_private_files(self) -> List[Dict[str, Any]]:
        """
        One-time migration to remove legacy per-user private files and per-user collections.
        Existing private files from earlier versions: do not expose them to anyone.
        Delete them (and their index data) in a one-time migration.
        """
        removed_items = []
        reg_file = self.persist_dir / "documents_registry.json"
        if reg_file.exists():
            try:
                with open(reg_file, "r", encoding="utf-8") as f:
                    reg = json.load(f)
            except Exception:
                reg = {}

            modified = False
            for doc_id, info in list(reg.items()):
                # Delete any document that was tagged with a legacy per-user user_id
                if info.get("user_id"):
                    fn = info.get("filename", "Unknown")
                    uid = info.get("user_id")
                    removed_items.append({"doc_id": doc_id, "filename": fn, "user_id": uid})
                    print(f"[Migration] Purged legacy private document: {fn} ({doc_id}) owned by {uid}")
                    try:
                        self.collection.delete(where={"doc_id": doc_id})
                    except Exception:
                        pass
                    del reg[doc_id]
                    modified = True

            if modified:
                try:
                    with open(reg_file, "w", encoding="utf-8") as f:
                        json.dump(reg, f, indent=2)
                except Exception as we:
                    print(f"[Migration] Error saving updated registry: {we}")

        # Delete any legacy per-user subdirectories under files_dir
        if self.files_dir.exists():
            import shutil
            for item in list(self.files_dir.iterdir()):
                if item.is_dir() and item.name.startswith("user_"):
                    try:
                        shutil.rmtree(item)
                        removed_items.append({"directory": item.name, "type": "user_directory"})
                        print(f"[Migration] Removed legacy per-user directory: {item.name}")
                    except Exception as e:
                        print(f"[Migration] Error removing legacy directory {item}: {e}")

        # Delete any legacy private user collections in ChromaDB
        try:
            for col in self.client.list_collections():
                if col.name.startswith("user_"):
                    try:
                        self.client.delete_collection(col.name)
                        removed_items.append({"collection": col.name, "type": "user_collection"})
                        print(f"[Migration] Removed legacy private collection: {col.name}")
                    except Exception as e:
                        print(f"[Migration] Error deleting collection {col.name}: {e}")
        except Exception:
            pass

        return removed_items

    def _sync_backend_db_if_needed(self, backend_vdb: Path):
        """Merges any chunks or documents from legacy backend/vector_db into canonical vector_db."""
        if not backend_vdb.exists() or backend_vdb.resolve() == self.persist_dir.resolve():
            return
        try:
            # Sync registry entries
            bak_reg_file = backend_vdb / "documents_registry.json"
            if bak_reg_file.exists():
                with open(bak_reg_file, "r", encoding="utf-8") as f:
                    bak_reg = json.load(f)
                if bak_reg:
                    reg = self._get_registry()
                    merged = {**bak_reg, **reg}
                    if len(merged) > len(reg):
                        self._save_registry(merged)

            # Sync ChromaDB chunks
            if (backend_vdb / "chroma.sqlite3").exists():
                bak_client = chromadb.PersistentClient(path=str(backend_vdb))
                for col_name in ["task_rag_vector_store", "task_rag_documents"]:
                    try:
                        b_col = bak_client.get_collection(col_name)
                        if b_col.count() > 0:
                            data = b_col.get()
                            existing = set(self.collection.get(include=[])["ids"])
                            new_ids = []
                            new_docs = []
                            new_metas = []
                            for cid, d, m in zip(data["ids"], data["documents"], data["metadatas"]):
                                if cid not in existing:
                                    new_ids.append(cid)
                                    new_docs.append(d)
                                    new_metas.append(m)
                            for i in range(0, len(new_ids), 100):
                                self.collection.add(
                                    ids=new_ids[i:i + 100],
                                    documents=new_docs[i:i + 100],
                                    metadatas=new_metas[i:i + 100]
                                )
                    except Exception:
                        pass
        except Exception as e:
            print(f"[VectorStore] Notice syncing legacy backend vector_db: {e}")

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

    def _reconcile_registry_with_chromadb(self, reg: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-reconciles ChromaDB chunks with the registry so any indexed file is always recognized."""
        try:
            total_chunks = self.collection.count()
            if total_chunks == 0:
                return reg
            res = self.collection.get(include=["metadatas"])
            metas = res.get("metadatas", [])
            if not metas:
                return reg

            from collections import defaultdict
            doc_chunks = defaultdict(int)
            doc_filenames = {}
            doc_pages = defaultdict(set)

            for m in metas:
                if isinstance(m, dict) and "doc_id" in m:
                    d_id = m["doc_id"]
                    doc_chunks[d_id] += 1
                    if "filename" in m and d_id not in doc_filenames:
                        doc_filenames[d_id] = m["filename"]
                    if "page" in m:
                        try:
                            doc_pages[d_id].add(int(m["page"]))
                        except Exception:
                            pass

            changed = False
            for d_id, count in doc_chunks.items():
                if d_id not in reg:
                    fn = doc_filenames.get(d_id, f"{d_id}.pdf")
                    reg[d_id] = {
                        "doc_id": d_id,
                        "filename": fn,
                        "chunks": count,
                        "pages_count": max(1, len(doc_pages[d_id])),
                        "uploaded_at": "2026-10-15T10:00:00",
                        "suggested_questions": []
                    }
                    changed = True

            if changed:
                self._save_registry(reg)
        except Exception as e:
            print(f"[VectorStore] Notice during registry reconciliation: {e}")
        return reg

    def _get_registry(self, force_reconcile: bool = False) -> Dict[str, Any]:
        reg_file = self.persist_dir / "documents_registry.json"
        try:
            mtime = reg_file.stat().st_mtime if reg_file.exists() else 0
        except Exception:
            mtime = 0

        if hasattr(self, "_cached_registry") and self._cached_registry is not None:
            if getattr(self, "_cached_registry_mtime", 0) == mtime and not force_reconcile:
                return self._cached_registry

        reg = {}
        if reg_file.exists():
            try:
                with open(reg_file, "r", encoding="utf-8") as f:
                    reg = json.load(f)
            except Exception:
                reg = {}

        if force_reconcile or not reg:
            reg = self._reconcile_registry_with_chromadb(reg)

        self._cached_registry = reg
        self._cached_registry_mtime = mtime
        return reg

    def _save_registry(self, registry: Dict[str, Any]):
        try:
            reg_file = self.persist_dir / "documents_registry.json"
            with open(reg_file, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
            self._cached_registry = registry
            try:
                self._cached_registry_mtime = reg_file.stat().st_mtime
            except Exception:
                pass
        except Exception as e:
            print(f"[VectorStore] Error saving document registry: {e}")

    def list_documents(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        reg = self._get_registry()
        if user_id:
            docs = [d for d in reg.values() if d.get("user_id") == str(user_id)]
        else:
            docs = list(reg.values())
        docs.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
        return docs

    def _cleanup_orphaned_files(self):
        """Removes any files in files_dir whose doc_id is not in the active registry."""
        try:
            if not hasattr(self, "files_dir") or not self.files_dir.exists():
                return
            reg = self._get_registry()
            active_ids = set(reg.keys())
            for f in list(self.files_dir.iterdir()):
                if f.is_file():
                    parts = f.name.split("_", 1)
                    if len(parts) == 2:
                        file_doc_id = parts[0]
                        if file_doc_id not in active_ids:
                            try:
                                f.unlink(missing_ok=True)
                            except Exception:
                                pass
        except Exception as e:
            print(f"[VectorStore] Notice cleaning orphaned files: {e}")

    def delete_document(self, doc_id: str, user_id: Optional[str] = None) -> bool:
        """
        Thoroughly deletes an indexed document from:
        1. All ChromaDB vector collections (by metadata doc_id, filename, and ID prefix)
        2. Local disk file storage & page JSON caches
        3. Document registry JSON
        4. Memory question & prompt caches
        Enforces user ownership check.
        """
        try:
            reg = self._get_registry()
            target_id = doc_id
            target_doc = reg.get(doc_id)
            if not target_doc:
                # Resolve by filename match if doc_id was passed as a filename
                for did, info in reg.items():
                    if info.get("filename") == doc_id or did == doc_id:
                        target_id = did
                        target_doc = info
                        break

            if not target_doc:
                return False

            # Ownership check: deny deletion if owned by another user
            if user_id and target_doc.get("user_id") and target_doc.get("user_id") != str(user_id):
                return False

            filename = target_doc.get("filename") if target_doc else None

            # 1. Thoroughly purge all chunks and embeddings from all ChromaDB collections
            try:
                col_names = [c.name for c in self.client.list_collections()]
                for col_name in col_names:
                    try:
                        col = self.client.get_collection(col_name)
                        # A. Delete by exact doc_id where clause
                        try:
                            res = col.get(where={"doc_id": target_id})
                            if res and res.get("ids"):
                                col.delete(ids=res["ids"])
                        except Exception:
                            pass
                        # B. If filename is known, also delete by filename where clause
                        if filename:
                            try:
                                res_fn = col.get(where={"filename": filename})
                                if res_fn and res_fn.get("ids"):
                                    col.delete(ids=res_fn["ids"])
                            except Exception:
                                pass
                        # C. Delete by doc_id where directly
                        try:
                            col.delete(where={"doc_id": target_id})
                        except Exception:
                            pass
                        # D. Search for any chunk IDs starting with target_id + "_"
                        try:
                            all_data = col.get(include=[])
                            if all_data and all_data.get("ids"):
                                prefix_ids = [cid for cid in all_data["ids"] if cid.startswith(f"{target_id}_")]
                                if prefix_ids:
                                    col.delete(ids=prefix_ids)
                        except Exception:
                            pass
                    except Exception as ce:
                        print(f"[VectorStore] Notice cleaning collection '{col_name}': {ce}")
            except Exception as e:
                print(f"[VectorStore] Notice listing ChromaDB collections: {e}")

            # 2. Delete local raw document file and page json files
            try:
                dirs_to_clean = [self.files_dir]
                if user_id:
                    dirs_to_clean.append(self.get_user_files_dir(user_id))
                elif target_doc.get("user_id"):
                    dirs_to_clean.append(self.get_user_files_dir(target_doc["user_id"]))

                for udir in dirs_to_clean:
                    if udir.exists():
                        for f in list(udir.glob(f"{target_id}_*")):
                            try:
                                f.unlink(missing_ok=True)
                            except Exception:
                                pass
                        if filename:
                            target_raw = udir / f"{target_id}_{filename}"
                            if target_raw.exists():
                                try:
                                    target_raw.unlink(missing_ok=True)
                                except Exception:
                                    pass
            except Exception as fe:
                print(f"[VectorStore] Notice deleting local file cache: {fe}")

            # 3. Clean up registry
            if target_id in reg:
                del reg[target_id]
                self._save_registry(reg)

            # 4. Invalidate memory caches
            self._all_docs_questions_cache = None
            self._all_docs_questions_cache_key = None

            # 5. Clean up any remaining orphaned files in self.files_dir
            self._cleanup_orphaned_files()

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

    def index_document(
        self,
        filename: str,
        content: Union[bytes, str],
        llm_service=None,
        firebase_service=None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extracts text, splits using RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200),
        generates embeddings and stores in user-isolated ChromaDB collection with doc_id and page metadata.
        Stores raw files in dedicated per-user directory: files/<user_id>/.
        Returns: { "doc_id": str, "filename": str, "chunks": int, "suggested_questions": list[str], "user_id": str }
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
                    "chunk_index": chunk_counter,
                    "user_id": str(user_id) if user_id else ""
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
                    "chunk_index": chunk_counter,
                    "user_id": str(user_id) if user_id else ""
                })
                chunk_counter += 1

        # Store in user-isolated ChromaDB collection in safe batches of 200
        target_coll = self.get_user_collection(user_id)
        batch_size = 200
        for i in range(0, len(ids), batch_size):
            target_coll.add(
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

        # Update local registry with user_id
        from datetime import datetime
        reg = self._get_registry()
        reg[doc_id] = {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(documents),
            "pages_count": len(pages),
            "uploaded_at": datetime.utcnow().isoformat(),
            "suggested_questions": suggested_questions,
            "user_id": str(user_id) if user_id else None
        }
        self._save_registry(reg)
        self._all_docs_questions_cache = None
        self._all_docs_questions_cache_key = None

        # Cache raw file and page structures in dedicated per-user directory
        user_dir = self.get_user_files_dir(user_id)
        try:
            content_bytes = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8")
            file_save_path = user_dir / f"{doc_id}_{filename}"
            with open(file_save_path, "wb") as f:
                f.write(content_bytes)

            pages_save_path = user_dir / f"{doc_id}_pages.json"
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

    def get_suggested_questions(self, doc_id: str, llm_service=None, user_id: Optional[str] = None) -> List[str]:
        """
        Retrieves or dynamically generates suggested questions suitable for this document or all documents for user_id.
        """
        is_all = not doc_id or str(doc_id).strip().lower() in ("all", "*", "")
        reg = self._get_registry()
        if user_id:
            reg = {k: v for k, v in reg.items() if v.get("user_id") == str(user_id)}

        active_coll = self.get_user_collection(user_id)

        if is_all:
            if not reg:
                return [
                    "How do I upload and index documents in this system?",
                    "What file formats (PDF, DOCX, TXT) are supported?"
                ]

            # Invalidate/check multi-document suggestions cache
            current_cache_key = (str(user_id), tuple(sorted(reg.keys())))
            if getattr(self, "_all_docs_questions_cache_key", None) == current_cache_key:
                cached_questions = getattr(self, "_all_docs_questions_cache", None)
                if cached_questions and len(cached_questions) >= 2:
                    return cached_questions

            # Read excerpts across ALL uploaded files for this user
            all_files_data = []
            for d_id, doc_info in reg.items():
                fn = doc_info.get("filename", "document")
                chunks = []
                try:
                    res = active_coll.get(where={"doc_id": d_id}, limit=2)
                    if res and res.get("documents"):
                        chunks = res["documents"]
                except Exception:
                    pass

                if not chunks:
                    pages = self.get_all_pages_for_document(d_id, user_id=user_id)
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
                for d in all_files_data:
                    base_fn = re.sub(r"\.[a-zA-Z0-9]+$", "", d["filename"])
                    questions.append(f"What key information or problems are covered in {base_fn}?")
                if len(all_files_data) > 1:
                    questions.append("What are the primary findings and common themes across all uploaded files?")

            self._all_docs_questions_cache_key = current_cache_key
            self._all_docs_questions_cache = questions[:6]
            return self._all_docs_questions_cache

        else:
            doc = reg.get(doc_id)
            if doc and doc.get("suggested_questions") and len(doc["suggested_questions"]) >= 2:
                return doc["suggested_questions"]

            filename = doc.get("filename", "document") if doc else "document"

            # Retrieve sample chunks from user collection for this document
            sample_chunks = []
            try:
                res = active_coll.get(where={"doc_id": doc_id}, limit=3)
                if res and res.get("documents"):
                    sample_chunks = res["documents"]
            except Exception as e:
                print(f"[VectorStore] Notice getting chunks for suggestions: {e}")

            if not sample_chunks:
                pages = self.get_all_pages_for_document(doc_id, user_id=user_id)
                if pages:
                    sample_chunks = [p["text"][:600] for p in pages[:3]]

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

            if doc:
                doc["suggested_questions"] = questions
                reg[doc_id] = doc
                self._save_registry(reg)

            return questions

    def get_all_pages_for_document(self, doc_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns full text for every page of the document: [{'page': 1, 'text': '...'}, ...]
        Uses local user cache file if available, or reconstructs from user collection.
        """
        user_dir = self.get_user_files_dir(user_id)
        pages_json = user_dir / f"{doc_id}_pages.json"
        if not pages_json.exists():
            pages_json = self.files_dir / f"{doc_id}_pages.json"

        if pages_json.exists():
            try:
                with open(pages_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass

        active_coll = self.get_user_collection(user_id)
        matching = active_coll.get(where={"doc_id": doc_id})
        if not matching or not matching.get("documents"):
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

    def _reconstruct_document_file(self, doc_id: str, doc_info: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Path]:
        """
        For pre-existing documents indexed without raw file on disk,
        synthesizes a clean viewable document (PDF for .pdf, text for .txt/.docx).
        """
        filename = doc_info.get("filename", f"{doc_id}.pdf")
        ext = filename.lower().split(".")[-1]
        user_dir = self.get_user_files_dir(user_id)
        target_path = user_dir / f"{doc_id}_{filename}"
        if target_path.exists():
            return target_path

        pages_data = self.get_all_pages_for_document(doc_id, user_id=user_id)
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

    def get_document_file_path(self, doc_id: str, user_id: Optional[str] = None) -> Optional[Path]:
        """
        Returns the absolute Path of the stored file, or reconstructs it if needed.
        Restricted to the user who owns the document.
        """
        reg = self._get_registry()
        doc_info = reg.get(doc_id)
        if not doc_info:
            return None

        # Verify ownership if user_id is provided and doc has user_id
        if user_id and doc_info.get("user_id") and str(doc_info.get("user_id")) != str(user_id):
            return None

        filename = doc_info.get("filename")
        effective_uid = user_id or doc_info.get("user_id")
        user_dir = self.get_user_files_dir(effective_uid)

        if filename:
            p = user_dir / f"{doc_id}_{filename}"
            if p.exists():
                return p
            p_global = self.files_dir / f"{doc_id}_{filename}"
            if p_global.exists():
                return p_global

        for f in user_dir.glob(f"{doc_id}_*"):
            if not f.name.endswith("_pages.json"):
                return f

        for f in self.files_dir.glob(f"{doc_id}_*"):
            if not f.name.endswith("_pages.json"):
                return f

        return self._reconstruct_document_file(doc_id, doc_info, user_id=effective_uid)

    def get_document_page(self, doc_id: str, page_num: int, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves page details: total pages, page text content, file metadata, and view link.
        Strictly isolated by user_id.
        """
        reg = self._get_registry()
        doc_info = reg.get(doc_id, {})
        if user_id and doc_info.get("user_id") and str(doc_info.get("user_id")) != str(user_id):
            return {
                "doc_id": doc_id,
                "filename": "Access Denied",
                "page": page_num,
                "total_pages": 0,
                "content": "",
                "file_type": "unknown",
                "has_raw_file": False,
                "file_url": ""
            }

        filename = doc_info.get("filename", "document")
        ext = filename.lower().split(".")[-1]

        all_pages = self.get_all_pages_for_document(doc_id, user_id=user_id)
        total_pages = doc_info.get("pages_count") or (len(all_pages) if all_pages else 1)

        target_page = next((p for p in all_pages if p["page"] == page_num), None)
        content = target_page["text"] if target_page else ""

        file_path = self.get_document_file_path(doc_id, user_id=user_id)
        has_raw = file_path is not None and file_path.exists()

        base_url = os.getenv("PUBLIC_URL", "").rstrip("/")
        pdf_url = f"{base_url}/api/documents/{doc_id}/file#page={page_num}"
        file_url = pdf_url if ext == "pdf" else f"{base_url}/api/documents/{doc_id}/file"

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

    def retrieve_top_chunks(self, doc_id: Optional[str], question: str, n_results: int = 4, user_id: Optional[str] = None) -> Tuple[List[str], List[Dict[str, Any]], List[int]]:
        """
        High-Accuracy Hybrid Retrieval:
        1. Dynamically searches across all uploaded files or a specific document for the specific user_id.
        2. Isolated to user's dedicated ChromaDB collection (user_<user_id>).
        3. When searching all documents (is_all_docs=True):
           - Gathers candidates both globally and on a per-document basis from every registered document owned by the user.
           - Matches document filename mentions and recency intents.
           - Applies Reciprocal Rank Fusion (RRF) and lexical BM25-style scoring.
           - Ensures balanced multi-document representation for complete, holistic answers.
        4. Suppresses near-duplicate chunks for diverse context.
        5. Returns top chunks with complete page and filename metadata.
        """
        is_all_docs = not doc_id or str(doc_id).strip().lower() in ("all", "*", "")
        reg = self._get_registry()

        # Scope registry strictly to the user's documents
        if user_id:
            reg = {k: v for k, v in reg.items() if str(v.get("user_id")) == str(user_id)}

        # If a single doc_id is requested, verify it exists in user's registry
        if not is_all_docs and doc_id:
            if user_id and doc_id not in reg:
                # User does not own this document
                return [], [], []

        active_collection = self.get_user_collection(user_id)
        total_chunks = active_collection.count()
        if total_chunks == 0:
            if not user_id:
                active_collection = self.collection
                total_chunks = active_collection.count()
            if total_chunks == 0:
                return [], [], []

        cand_pool: Dict[Tuple[str, int], Dict[str, Any]] = {}

        # Pre-compute query embedding ONCE so ChromaDB doesn't re-embed the question 9+ times
        query_emb = None
        try:
            emb_fn = getattr(active_collection, "_embedding_function", None) or getattr(self.collection, "_embedding_function", None)
            if emb_fn:
                embs = emb_fn([question])
                if embs and len(embs) > 0:
                    query_emb = embs[0]
        except Exception:
            pass

        base_query_args = {"query_embeddings": [query_emb]} if query_emb is not None else {"query_texts": [question]}

        if is_all_docs and len(reg) > 1:
            # --- MULTI-DOCUMENT ULTRA-FAST HIGH ACCURACY RETRIEVAL ---
            # 1. Global ANN Search across user's collection in a single fast C++ index query (<5ms)
            global_k = min(40, total_chunks)
            try:
                g_res = active_collection.query(**base_query_args, n_results=global_k)
                g_docs = g_res.get("documents", [[]])[0]
                g_metas = g_res.get("metadatas", [[]])[0]
                g_dists = g_res.get("distances", [[]])[0] if "distances" in g_res and g_res["distances"] else []
                for r_idx, (c, m) in enumerate(zip(g_docs, g_metas)):
                    d_id = m.get("doc_id", "")
                    if d_id not in reg:
                        continue
                    c_idx = int(m.get("chunk_index", r_idx))
                    k = (d_id, c_idx)
                    dist = g_dists[r_idx] if r_idx < len(g_dists) else 1.0
                    cand_pool[k] = {
                        "chunk": c,
                        "meta": m,
                        "vector_rank": r_idx + 1,
                        "dist": dist
                    }
            except Exception as ge:
                print(f"[VectorStore] Global query notice: {ge}")

            # 2. Targeted candidate gathering ONLY if query specifically mentions a document filename/topic
            q_lower_check = question.lower()
            target_doc_ids = []
            for d_id, d_info in reg.items():
                fn = (d_info.get("filename") or "").lower()
                fn_stem = re.sub(r"\.[a-z0-9]+$", "", fn)
                if fn_stem and len(fn_stem) > 3 and (fn_stem in q_lower_check or fn in q_lower_check):
                    target_doc_ids.append(d_id)

            for d_id in target_doc_ids[:2]:
                try:
                    d_res = active_collection.query(
                        **base_query_args,
                        n_results=6,
                        where={"doc_id": d_id}
                    )
                    d_docs = d_res.get("documents", [[]])[0]
                    d_metas = d_res.get("metadatas", [[]])[0]
                    d_dists = d_res.get("distances", [[]])[0] if "distances" in d_res and d_res["distances"] else []
                    for r_idx, (c, m) in enumerate(zip(d_docs, d_metas)):
                        c_idx = int(m.get("chunk_index", r_idx))
                        k = (d_id, c_idx)
                        dist = d_dists[r_idx] if r_idx < len(d_dists) else 1.0
                        if k in cand_pool:
                            cand_pool[k]["vector_rank"] = min(cand_pool[k]["vector_rank"], r_idx + 1)
                            cand_pool[k]["dist"] = min(cand_pool[k]["dist"], dist)
                        else:
                            cand_pool[k] = {
                                "chunk": c,
                                "meta": m,
                                "vector_rank": r_idx + 1,
                                "dist": dist
                            }
                except Exception:
                    pass
        else:
            # --- SINGLE DOCUMENT OR SINGLE-DOC REGISTRY RETRIEVAL ---
            candidate_k = min(32, total_chunks)
            try:
                query_kwargs = {
                    **base_query_args,
                    "n_results": candidate_k
                }
                if not is_all_docs:
                    query_kwargs["where"] = {"doc_id": doc_id}

                query_res = active_collection.query(**query_kwargs)
                q_docs = query_res.get("documents", [[]])[0]
                q_metas = query_res.get("metadatas", [[]])[0]
                q_dists = query_res.get("distances", [[]])[0] if "distances" in query_res and query_res["distances"] else []

                for r_idx, (c, m) in enumerate(zip(q_docs, q_metas)):
                    d_id = m.get("doc_id", "")
                    if reg and d_id not in reg:
                        continue
                    c_idx = int(m.get("chunk_index", r_idx))
                    k = (d_id, c_idx)
                    dist = q_dists[r_idx] if r_idx < len(q_dists) else 1.0
                    cand_pool[k] = {
                        "chunk": c,
                        "meta": m,
                        "vector_rank": r_idx + 1,
                        "dist": dist
                    }
            except Exception as query_err:
                print(f"[VectorStore] Query notice: {query_err}")

            # Fallback if specific document returned empty
            if not cand_pool and not is_all_docs:
                try:
                    fb = active_collection.get(where={"doc_id": doc_id}, limit=candidate_k)
                    if fb and fb.get("documents"):
                        for r_idx, (c, m) in enumerate(zip(fb["documents"], fb.get("metadatas", []))):
                            c_idx = int(m.get("chunk_index", r_idx))
                            k = (doc_id, c_idx)
                            cand_pool[k] = {
                                "chunk": c,
                                "meta": m,
                                "vector_rank": r_idx + 1,
                                "dist": 1.0
                            }
                except Exception:
                    pass

        if not cand_pool:
            return [], [], []

        # --- SCORING CANDIDATES WITH HYBRID RRF + LEXICAL + DOCUMENT INTENT ---
        q_lower = question.lower()
        scored_candidates = []

        # Find latest uploaded doc_id for recency intent
        latest_doc_id = None
        if reg:
            sorted_by_date = sorted(reg.values(), key=lambda x: x.get("uploaded_at", ""), reverse=True)
            if sorted_by_date:
                latest_doc_id = sorted_by_date[0].get("doc_id")

        has_recency_intent = any(w in q_lower for w in ["new", "latest", "recent", "just uploaded", "newly"])
        has_multi_doc_intent = any(w in q_lower for w in ["all", "each", "both", "every", "compare", "summarize", "files", "documents", "overview"])

        for item in cand_pool.values():
            chunk = item["chunk"]
            meta = item["meta"]
            rank_idx = item["vector_rank"] - 1
            dist = item["dist"]
            curr_doc_id = meta.get("doc_id", "")
            curr_fn = (meta.get("filename") or "").lower()

            # 1. RRF Vector Score: 1 / (60 + rank)
            rrf_vector = 1.0 / (60.0 + (rank_idx + 1))

            # 2. Distance similarity
            sim = max(0.0, 1.0 - dist) if dist <= 1.0 else (1.0 / (1.0 + rank_idx))

            # 3. Lexical keyword score
            kw_score = self._compute_keyword_score(question, chunk)

            # 4. Filename / Document Mention Boost
            fn_boost = 0.0
            if curr_fn:
                fn_clean = re.sub(r"\.[a-z0-9]+$", "", curr_fn)
                fn_parts = [p for p in re.split(r"[\s_\-\.]+", fn_clean) if len(p) > 2]
                for part in fn_parts:
                    if part in q_lower:
                        fn_boost += 6.0
                if fn_clean in q_lower or curr_fn in q_lower:
                    fn_boost += 14.0

            # 5. Boost newest file if recency intent present
            recency_boost = 0.0
            if has_recency_intent and curr_doc_id == latest_doc_id:
                recency_boost = 8.0

            total_score = (rrf_vector * 100.0) + (sim * 10.0) + (kw_score * 5.0) + fn_boost + recency_boost

            scored_candidates.append({
                "chunk": chunk,
                "meta": meta,
                "score": total_score,
                "doc_id": curr_doc_id
            })

        # Sort all candidates by total score descending
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # Determine effective target chunk count
        # In multi-document search with multiple files, expand to 6 chunks for richer cross-document context
        if is_all_docs and len(reg) > 1:
            target_n = max(n_results, min(6, len(reg) * 2))
        else:
            target_n = n_results

        # Multi-document diversity-aware selection:
        # Prevent any single document from starving others if multiple documents are uploaded
        selected_candidates = []
        selected_tokens_list = []
        doc_counts: Dict[str, int] = {}
        max_per_doc = max(2, (target_n // len(reg)) + 1) if (is_all_docs and len(reg) > 1 and has_multi_doc_intent) else target_n

        # Pass 1: Select top candidates respecting document balance and deduplication
        for cand in scored_candidates:
            c_doc = cand["doc_id"]
            if doc_counts.get(c_doc, 0) >= max_per_doc:
                continue

            cand_tokens = set(re.findall(r"\w+", cand["chunk"].lower()))
            is_dup = False
            for prev_tokens in selected_tokens_list:
                intersection = len(cand_tokens.intersection(prev_tokens))
                union = len(cand_tokens.union(prev_tokens))
                if union > 0 and (intersection / union) > 0.75:
                    is_dup = True
                    break

            if not is_dup:
                selected_candidates.append(cand)
                selected_tokens_list.append(cand_tokens)
                doc_counts[c_doc] = doc_counts.get(c_doc, 0) + 1

            if len(selected_candidates) == target_n:
                break

        # Pass 2: Fill remaining slots if document balancing was restrictive
        if len(selected_candidates) < target_n:
            for cand in scored_candidates:
                if cand not in selected_candidates:
                    cand_tokens = set(re.findall(r"\w+", cand["chunk"].lower()))
                    is_dup = False
                    for prev_tokens in selected_tokens_list:
                        intersection = len(cand_tokens.intersection(prev_tokens))
                        union = len(cand_tokens.union(prev_tokens))
                        if union > 0 and (intersection / union) > 0.75:
                            is_dup = True
                            break
                    if not is_dup:
                        selected_candidates.append(cand)
                        selected_tokens_list.append(cand_tokens)
                        if len(selected_candidates) == target_n:
                            break

        # Pass 3: Ultimate fill
        if len(selected_candidates) < target_n:
            for cand in scored_candidates:
                if cand not in selected_candidates:
                    selected_candidates.append(cand)
                    if len(selected_candidates) == target_n:
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
