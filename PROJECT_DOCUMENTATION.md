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
│   ├── main.py                         # Primary FastAPI application and route orchestrator
│   ├── rag_service.py                  # Standalone RAG implementation
│   ├── requirements.txt                # Python dependencies (FastAPI, PyMuPDF, python-docx, ChromaDB, etc.)
│   ├── test_full_suite.py              # Automated 8-phase comprehensive API test suite
│   ├── test_e2e.py                     # End-to-end integration test suite
│   ├── test_llm.py                     # LLM synthesis test script
│   ├── test_retrieve.py                # Retrieval verification script
│   ├── pages/                          # Modular FastAPI Page Routers & Schemas
│   │   ├── __init__.py                 # Router exports
│   │   ├── health.py                   # Health check & system diagnostics endpoint
│   │   ├── upload.py                   # Document upload & asynchronous indexing
│   │   ├── documents.py                # Documents registry, file streaming, & page inspection
│   │   ├── chat.py                     # Chat question-answering, RRF retrieval & grounding
│   │   ├── schemas.py                  # Pydantic request/response data contracts
│   │   └── deps.py                     # Singleton dependencies injection (vector_store, llm_service)
│   ├── app/
│   │   ├── __init__.py                 # Package marker
│   │   ├── main.py                     # App wrapper
│   │   └── services/
│   │       ├── __init__.py             # Service package marker
│   │       ├── chat_history_service.py # SQLite persistent storage for chat messages per document
│   │       ├── firebase_service.py     # Optional Firebase Firestore / Cloud Storage sync
│   │       ├── llm_service.py          # LLM prompt synthesis, multi-file suggestions & API caller
│   │       └── vector_store.py         # PyMuPDF/python-docx parser, chunker & ChromaDB hybrid RRF store
│   └── vector_db/                      # Persistent local ChromaDB & SQLite storage (gitignored)
│       ├── chroma.sqlite3              # ChromaDB metadata and SQLite collections
│       ├── chat_history.db             # SQLite database storing chat messages per doc_id
│       ├── documents_registry.json     # Metadata registry of all indexed documents & cached questions
│       └── files/                      # Cached raw files & pages structures for instant viewing
│
├── frontend/                           # React + Vite Frontend Application
│   ├── index.html                      # Single-page HTML shell with Google Fonts
│   ├── package.json                    # Node dependencies and build scripts
│   ├── vite.config.js                  # Vite bundler configuration
│   ├── tailwind.config.js              # Tailwind CSS theme & color palette
│   ├── postcss.config.js               # PostCSS plugin settings
│   ├── public/                         # Static icons and assets
│   └── src/
│       ├── main.jsx                    # React DOM entrypoint
│       ├── App.jsx                     # Master application shell, tab routing & active document state
│       ├── App.css                     # Custom animations, glow utility styles, and scrollbars
│       ├── index.css                   # Core design system & Tailwind directives
│       ├── api.js                      # Centralized API service connecting to FastAPI backend
│       ├── assets/                     # Graphic assets and logos
│       ├── pages/                      # Dedicated Top-Level Pages
│       │   ├── ChatPage.jsx            # Main interactive chat & question-answering page
│       │   ├── DocumentsPage.jsx       # Document management, metadata cards & inline viewing
│       │   ├── SystemPage.jsx          # Live system diagnostics, ChromaDB stats & provider status
│       │   └── UploadPage.jsx          # Full drag-and-drop file upload & format guidance
│       └── components/
│           ├── ChatWindow.jsx          # Right panel markdown chat, citations, suggestions & clear chat
│           ├── DocumentSidebar.jsx     # Document switcher sidebar with format badges
│           ├── DocumentPageModal.jsx   # In-app document viewer modal for cited pages
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
  - `add_message(doc_id, role, content, sources, source_details, suggested_questions)`: Inserts user or assistant turns with rich page source citations and follow-up prompts.
  - `get_messages(doc_id)`: Retrieves all chronological messages for the selected document or 'all'.
  - `clear_messages(doc_id)`: Deletes conversation records when the user clicks "Clear Chat" or deletes a document.

#### [`llm_service.py`](file:///e:/Task-RAG/backend/app/services/llm_service.py)
- **Role**: Generative AI orchestration, strict context synthesis, multi-file suggestions, and connection pooling.
- **Key Methods**:
  - `generate_suggested_questions(filename, sample_chunks)`: Analyzes sample chunks of a document to generate 3 to 4 specific, relevant, non-generic prompt questions tailored to that exact document.
  - `generate_all_documents_suggested_questions(all_files_data)`: Synthesizes excerpts across **all uploaded files** to generate 4 to 6 relevant questions representing each distinct document and cross-document themes for the main page.
  - `generate_answer(question, chunks, metadatas)`: Queries Google Gemini (`gemini-3.5-flash-lite`, `gemini-flash-lite-latest`), OpenAI (`gpt-4o-mini`), or offline extractive synthesis with strict zero-hallucination guardrails and page citation cleaning.
  - `generate_sequential_questions(filename, question, answer, chunks)`: Generates 3 intelligent follow-up questions based on the answer and context.

#### [`vector_store.py`](file:///e:/Task-RAG/backend/app/services/vector_store.py)
- **Role**: Document ingestion, multi-format text extraction, chunking, and high-speed hybrid search.
- **Key Methods**:
  - `extract_text_with_page_metadata(filename, content)`:
    - **PDF**: PyMuPDF (`pymupdf as fitz`) with `sort=True` for layout-aware reading order and running header/footer stripping.
    - **DOCX / DOC**: `python-docx` extraction of paragraphs, headings, and table cells, plus fallback stream extraction. Segments text into logical ~2000-character pages.
    - **TXT / MD**: Structured section detection and ~2500-character virtual page segmentation.
  - `index_document(filename, content, llm_service)`: Splits extracted text with `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`, creates ONNX embeddings, indexes into ChromaDB in batches, generates dynamic suggested questions, saves document metadata, and caches raw files.
  - `retrieve_top_chunks(doc_id, question, n_results)`: Executes direct ChromaDB query combining dense similarity with BM25 keyword, numerical, and acronym scoring via Reciprocal Rank Fusion (RRF).
  - `get_suggested_questions(doc_id, llm_service)`: For single document, returns file-specific questions; for `all` (main page), aggregates excerpts from all files and generates questions spanning all documents with zero-latency caching.

---

### 3. Backend REST API Endpoints ([`backend/main.py`](file:///e:/Task-RAG/backend/main.py))

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | API status and root information. |
| `GET` | `/api/health` | Live system health check, indexed document count, vector DB path, and active LLM status. |
| `GET` | `/api/documents` | Lists all indexed documents with chunk counts, page counts, and metadata. |
| `DELETE` | `/api/documents/{doc_id}` | Deletes a document from ChromaDB, registry, and purges its chat history. |
| `GET` | `/api/documents/{doc_id}/suggested-questions` | Returns dynamic questions tailored to the document (or all documents if `doc_id="all"`). |
| `GET` | `/api/documents/{doc_id}/pages/{page_num}` | Retrieves full text content, metadata, and viewing URLs for a specific document page. |
| `GET` | `/api/documents/{doc_id}/file` | Streams raw file inline with PDF `#page=X` browser jump support. |
| `GET` | `/api/documents/{doc_id}/file/{filename}` | Streams raw file with explicit filename for browser deep-linking. |
| `GET` | `/api/documents/{doc_id}/chat` | Retrieves persistent SQLite conversation history for the specified file. |
| `DELETE` | `/api/documents/{doc_id}/chat` | Clears SQLite conversation history for the specified file. |
| `POST` | `/api/upload` | Uploads and indexes `.pdf`, `.txt`, `.docx`, or `.doc` file asynchronously. |
| `POST` | `/api/ask` | Accepts `{ doc_id, question }`, persists user turn, retrieves top 4 RRF chunks, generates answer, persists assistant turn, and returns `{ answer, sources, source_details, suggested_questions }`. |
| `POST` | `/api/chat/sequential` | Generates 3 sequential follow-up questions given a document question and context. |

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
