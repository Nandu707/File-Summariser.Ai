# Task-RAG / File Summariser.Ai: Complete Project & File Reference Guide

This document provides a comprehensive overview of every file in the **Task-RAG (File Summariser.Ai)** codebase, explaining its architectural role, its functionality, and the code or configuration it contains.

---

## Architecture Overview

**File Summariser.Ai** is an end-to-end full-stack Retrieval-Augmented Generation (RAG) system built with:
- **Backend**: FastAPI (Python 3.11+), PyMuPDF (`fitz`), `python-docx` (Word document ingestion), ChromaDB (persistent local vector database), SQLite (persistent chat history per document), LangChain Text Splitters, Google Gemini & OpenAI API clients with deterministic grounding.
- **Frontend**: React 18, Vite, Tailwind CSS, Lucide React icons, Axios, and React-Markdown.
- **Core Capabilities**:
  - Multi-format document ingestion: **PDF**, **Plain Text (.txt)**, **Markdown (.md)**, and **Word Documents (.docx, .doc)**.
  - Hybrid Reciprocal Rank Fusion (RRF) search combining dense vector embeddings with BM25 lexical scoring for exact figures, numbers, and acronyms.
  - Dynamic, document-tailored suggested questions generated upon upload and document selection.
  - Full per-document persistent conversation history stored in SQLite (`chat_history.db`).
  - Active generation lock: prevents accidental document switching while answers are loading.
  - Consumer-grade UI without exposed raw internal IDs or technical clutter.

---

## Directory Tree

```
Task-RAG/
├── .env                                # Local environment secrets (API keys, ports) - NOT committed
├── .env.example                        # Safe template for environment configuration
├── .gitignore                          # Git ignore for venv, node_modules, vector_db, secrets
├── package.json                        # Root package scripts for concurrent full-stack dev
├── README.md                           # Quickstart guide and API summary
├── PROJECT_DOCUMENTATION.md            # Complete file-by-file reference guide (this file)
├── PROJECT_PROCESSES.md                # System data pipelines, RRF algorithms, and lifecycles
├── PROJECT_TECHNOLOGIES.md             # Technology stack rationale and trade-offs
├── PROJECT_CHANGELOG.md                # Complete evolution and chronological changes log
│
├── app/                                # Root mirror of backend service modules
│   ├── __init__.py                     # Python package marker
│   ├── main.py                         # Root entrypoint delegate
│   └── services/
│       ├── __init__.py                 # Services package marker
│       ├── chat_history_service.py     # SQLite persistent storage for chat messages per document
│       ├── llm_service.py              # LLM prompt synthesis, dynamic questions & API caller
│       └── vector_store.py             # PyMuPDF/python-docx parser, chunker & ChromaDB hybrid RRF store
│
├── backend/                            # FastAPI Backend Service
│   ├── .env                            # Backend environment variables (API keys, ports)
│   ├── .env.example                    # Environment variable template
│   ├── main.py                         # Primary FastAPI application and REST endpoints
│   ├── rag_service.py                  # Standalone/legacy RAG implementation
│   ├── requirements.txt                # Python dependencies (FastAPI, PyMuPDF, python-docx, ChromaDB, etc.)
│   ├── test_e2e.py                     # End-to-end integration test suite
│   ├── test_llm.py                     # LLM synthesis test script
│   ├── test_retrieve.py                # Retrieval verification script
│   ├── app/
│   │   ├── __init__.py                 # Package marker
│   │   ├── main.py                     # App wrapper
│   │   └── services/
│   │       ├── __init__.py             # Service package marker
│   │       ├── chat_history_service.py # SQLite persistent storage for chat messages per document
│   │       ├── llm_service.py          # LLM prompt synthesis, dynamic questions & API caller
│   │       └── vector_store.py         # PyMuPDF/python-docx parser, chunker & ChromaDB hybrid RRF store
│   └── vector_db/                      # Persistent local ChromaDB & SQLite storage (gitignored)
│       ├── chroma.sqlite3              # ChromaDB metadata and SQLite collections
│       ├── chat_history.db             # SQLite database storing chat messages per doc_id
│       ├── documents_registry.json     # Metadata registry of all indexed documents & cached questions
│       └── [uuid-collections]/         # Binary HNSW vector indices
│
├── frontend/                           # React + Vite Frontend Application
│   ├── index.html                      # Single-page HTML shell with Google Fonts
│   ├── package.json                    # Node dependencies and build scripts
│   ├── vite.config.js                  # Vite bundler configuration
│   ├── tailwind.config.js              # Tailwind CSS theme & color palette
│   ├── postcss.config.js               # PostCSS plugin settings
│   ├── public/                         # Static icons and assets
│   │   ├── favicon.svg                 # Application favicon
│   │   └── icons.svg                   # SVG icon spritesheet
│   └── src/
│       ├── main.jsx                    # React DOM entrypoint
│       ├── App.jsx                     # Master split-screen layout component & answering state
│       ├── App.css                     # Custom animations, glow utility styles, and scrollbars
│       ├── index.css                   # Core design system & Tailwind directives
│       ├── api.js                      # Centralized API service connecting to FastAPI backend
│       ├── assets/                     # Graphic assets and logos
│       └── components/
│           ├── FileUploader.jsx        # Left sidebar uploader, drag-and-drop, and document list
│           ├── ChatWindow.jsx          # Right panel markdown chat, citations, suggestions & clear chat
│           ├── ChatArea.jsx            # Reusable chat interface variant
│           ├── DocumentSidebar.jsx     # Reusable document browser sidebar variant with format badges
│           ├── Navbar.jsx              # Navigation header bar with live backend health monitor
│           └── UploadModal.jsx         # Modal dialog variant for multi-format file upload
│
└── test_docs/                          # Test documents for RAG validation
    ├── sample_ai_report.pdf            # Multi-page PDF test document
    └── sample_quantum_computing.txt    # Multi-section TXT test document
```

---

## Detailed File-by-File Breakdown

### 1. Root Configuration & Project Files

#### [`/.gitignore`](file:///e:/Task-RAG/.gitignore)
- **Role**: Prevents committing sensitive credentials, virtual environments, compiled caches, and local databases to GitHub.
- **Ignored Entries**: `.env`, `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `vector_db/`, `*.db`, `*.sqlite3`, `documents_registry.json`, `chat_history.db`.

#### [`/.env.example`](file:///e:/Task-RAG/.env.example)
- **Role**: Safe public template outlining required environment variables for users setting up the project from scratch.

#### [`/package.json`](file:///e:/Task-RAG/package.json)
- **Role**: Root package orchestrator for concurrent full-stack development (`npm run dev`).

#### [`/README.md`](file:///e:/Task-RAG/README.md)
- **Role**: Project overview, architectural documentation, setup commands, and API contract specifications.

---

### 2. Backend Services (`backend/app/services/` & `app/services/`)

#### [`chat_history_service.py`](file:///e:/Task-RAG/backend/app/services/chat_history_service.py)
- **Role**: Persistent conversation storage backed by SQLite (`vector_db/chat_history.db`).
- **Core Methods**:
  - `add_message(doc_id, role, content, sources, is_error, timestamp)`: Inserts user or assistant turns with JSON-encoded page source citations.
  - `get_messages(doc_id)`: Retrieves all chronological messages for the selected document.
  - `clear_messages(doc_id)`: Deletes conversation records when the user clicks "Clear Chat" or deletes a document.

#### [`llm_service.py`](file:///e:/Task-RAG/backend/app/services/llm_service.py)
- **Role**: Generative AI orchestration, strict context synthesis, and dynamic suggested question generation.
- **Key Methods**:
  - `generate_suggested_questions(filename, sample_chunks)`: Analyzes sample chunks of a document to generate 3 to 4 specific, relevant, non-generic prompt questions tailored to that exact document (e.g., candidate skills for a resume, methodology for a research paper, system architecture for a technical report).
  - `generate_answer(question, chunks, metadatas)`: Queries Google Gemini (`gemini-2.5-flash`), OpenAI (`gpt-4o-mini`), or offline extractive synthesis with strict zero-hallucination guardrails and page citation requirements (`(Page X)`).

#### [`vector_store.py`](file:///e:/Task-RAG/backend/app/services/vector_store.py)
- **Role**: Document ingestion, multi-format text extraction, chunking, and hybrid search.
- **Key Methods**:
  - `_extract_pages_from_content(filename, content)`:
    - **PDF**: PyMuPDF (`fitz.open`) with `sort=True` for layout-aware reading order and running header/footer stripping.
    - **DOCX / DOC**: `python-docx` extraction of paragraphs, headings, and table cells, plus fallback stream extraction. Segments text into logical ~2000-character pages for accurate page-level citations.
    - **TXT / MD**: Structured section detection and ~2500-character virtual page segmentation.
  - `index_document(filename, content, llm_service)`: Splits extracted text with `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`, creates ONNX embeddings, indexes into ChromaDB in batches of 200 chunks, generates dynamic suggested questions, and saves document metadata into `documents_registry.json`.
  - `retrieve_top_chunks(doc_id, question, n_results)`: Executes Reciprocal Rank Fusion (RRF) combining dense cosine similarity with BM25 keyword, numerical, and acronym scoring.
  - `get_suggested_questions(doc_id, llm_service)`: Fetches cached suggested questions or generates and stores them on-demand.

---

### 3. Backend REST API Endpoints ([`backend/main.py`](file:///e:/Task-RAG/backend/main.py))

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | API status and root information. |
| `GET` | `/api/health` | Live system health check, indexed document count, and active LLM status. |
| `GET` | `/api/documents` | Lists all indexed documents with chunk counts, page counts, and metadata. |
| `DELETE` | `/api/documents/{doc_id}` | Deletes a document from ChromaDB, registry, and purges its chat history. |
| `GET` | `/api/documents/{doc_id}/suggested-questions` | Returns 3–4 dynamic questions tailored to the document. |
| `GET` | `/api/documents/{doc_id}/chat` | Retrieves persistent SQLite conversation history for the specified file. |
| `DELETE` | `/api/documents/{doc_id}/chat` | Clears SQLite conversation history for the specified file. |
| `POST` | `/api/upload` | Uploads and indexes `.pdf`, `.txt`, `.docx`, or `.doc` file asynchronously. |
| `POST` | `/api/ask` | Accepts `{ doc_id, question }`, persists user turn, retrieves top 4 RRF chunks, generates answer, persists assistant turn, and returns `{ answer, sources }`. |

---

### 4. Frontend Application Components (`frontend/src/`)

#### [`App.jsx`](file:///e:/Task-RAG/frontend/src/App.jsx)
- **Role**: Root split-screen layout orchestrator.
- **State**: Tracks active `docId`, `documentInfo`, backend health polling, and `isAnswering` lock state.

#### [`components/FileUploader.jsx`](file:///e:/Task-RAG/frontend/src/components/FileUploader.jsx)
- **Role**: Left sidebar document upload dropzone and document switcher.
- **Features**:
  - Drag-and-drop and file input supporting `.pdf`, `.txt`, `.docx`, and `.doc`.
  - Dynamic format badges: **PDF** (red), **TXT** (emerald), and **DOCX / DOC** (indigo/blue).
  - Lock state: Prevents file switching while an answer is actively being generated.
  - Clean display: No technical `doc_id` exposed to users.

#### [`components/ChatWindow.jsx`](file:///e:/Task-RAG/frontend/src/components/ChatWindow.jsx)
- **Role**: Right panel markdown conversation interface.
- **Features**:
  - Automatically loads persistent conversation history from SQLite whenever a file is selected.
  - Displays dynamic suggested questions tailored to the active file when no chat messages exist.
  - "Clear Chat" button in the header allowing users to reset document conversation on demand.
  - Clickable citation badges (`Page X`) that notify and highlight the source page.
  - Custom vertical scrollbar on the chat container and ask input area.
  - Fully locked send button and file-switching during answer generation.

#### [`components/DocumentSidebar.jsx`](file:///e:/Task-RAG/frontend/src/components/DocumentSidebar.jsx) & [`components/UploadModal.jsx`](file:///e:/Task-RAG/frontend/src/components/UploadModal.jsx)
- Reusable modal dialog and sidebar variants supporting multi-format files and format badges.

#### [`api.js`](file:///e:/Task-RAG/frontend/src/api.js)
- Clean, centralized Fetch/Axios API client wrappers for all backend endpoints.
