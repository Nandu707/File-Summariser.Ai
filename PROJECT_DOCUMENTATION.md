# Task-RAG: Complete Project & File Reference Guide

This document provides a comprehensive overview of every file in the **Task-RAG** codebase, explaining its architectural role, its functionality, and the code or configuration it contains.

---

## Architecture Overview

**Task-RAG** is an end-to-end full-stack Retrieval-Augmented Generation (RAG) system built with:
- **Backend**: FastAPI (Python 3.11+), PyMuPDF (`fitz`), ChromaDB (persistent local vector database), LangChain Text Splitters, Google Gemini & OpenAI API clients with deterministic grounding.
- **Frontend**: React 18, Vite, Tailwind CSS, Lucide React icons, Axios, and React-Markdown.
- **Design Pattern**: Split-Screen UI with persistent document selection, drag-and-drop ingestion, non-blocking asynchronous processing, and hybrid reciprocal rank fusion (RRF) retrieval.

---

## Directory Tree

```
Task-RAG/
├── .env                                # Root environment configuration file
├── package.json                        # Root package scripts for concurrent full-stack dev
├── PROJECT_DOCUMENTATION.md            # Complete project documentation (this file)
├── README.md                           # Quickstart guide and API summary
│
├── app/                                # Root mirror of backend service modules
│   ├── __init__.py                     # Python package marker
│   ├── main.py                         # Root entrypoint delegate
│   └── services/
│       ├── __init__.py                 # Services package marker
│       ├── llm_service.py              # LLM prompt synthesis & API caller
│       └── vector_store.py             # PyMuPDF parser, chunker & ChromaDB hybrid RRF store
│
├── backend/                            # FastAPI Backend Service
│   ├── .env                            # Backend environment variables (API keys, ports)
│   ├── .env.example                    # Environment variable template
│   ├── main.py                         # Primary FastAPI application and REST endpoints
│   ├── rag_service.py                  # Standalone/legacy RAG implementation
│   ├── requirements.txt                # Python dependencies
│   ├── app/
│   │   ├── __init__.py                 # Package marker
│   │   ├── main.py                     # App wrapper
│   │   └── services/
│   │       ├── __init__.py             # Service package marker
│   │       ├── llm_service.py          # LLM prompt synthesis & API caller
│   │       └── vector_store.py         # PyMuPDF parser, chunker & ChromaDB hybrid RRF store
│   └── vector_db/                      # Persistent local ChromaDB storage
│       ├── chroma.sqlite3              # ChromaDB metadata and SQLite collections
│       ├── documents_registry.json     # Metadata registry of all indexed documents
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
│       ├── App.jsx                     # Master split-screen layout component
│       ├── App.css                     # Custom animations and glow utility styles
│       ├── index.css                   # Core design system & Tailwind directives
│       ├── api.js                      # Axios API helper functions
│       ├── assets/                     # Graphic assets and logos
│       └── components/
│           ├── FileUploader.jsx        # Left sidebar uploader & document switcher
│           ├── ChatWindow.jsx          # Right panel markdown chat & citation badges
│           ├── ChatArea.jsx            # Reusable chat interface variant
│           ├── DocumentSidebar.jsx     # Reusable document browser sidebar variant
│           ├── Navbar.jsx              # Navigation header bar
│           └── UploadModal.jsx         # Modal dialog variant for file upload
│
└── test_docs/                          # Test documents for RAG validation
    ├── sample_ai_report.pdf            # Multi-page PDF test document
    └── sample_quantum_computing.txt    # Multi-section TXT test document
```

---

## Detailed File-by-File Breakdown

### 1. Root Files

#### [`/.env`](file:///e:/Task-RAG/.env)
- **Role**: Root environment variable store.
- **Contents**:
  - `CHROMA_PERSIST_DIRECTORY=./vector_db`: Specifies where ChromaDB stores persistent SQLite files and indices.
  - `CORS_ORIGIN=http://localhost:5173`: Allowed origin for frontend-to-backend requests.
  - `GEMINI_API_KEY`: API key for Google Gemini generative AI models (`gemini-3.5-flash-lite`, `models/gemini-3.8-flash`).
  - `OPENAI_API_KEY`: API key for OpenAI GPT models (`gpt-4o-mini`).

#### [`/package.json`](file:///e:/Task-RAG/package.json)
- **Role**: Root package orchestrator.
- **Contents**: Provides root `npm run dev` script to run both backend and frontend development servers concurrently.

#### [`/README.md`](file:///e:/Task-RAG/README.md)
- **Role**: Project overview, architectural documentation, and setup instructions.
- **Contents**: Explains the monorepo structure, API contracts (`POST /api/upload`, `POST /api/ask`), installation steps, and environment configuration.

---

### 2. Backend Services (`/backend`)

#### [`/backend/main.py`](file:///e:/Task-RAG/backend/main.py)
- **Role**: Primary FastAPI application entrypoint and REST API router.
- **What is in this file**:
  - **CORS Configuration**: Explicitly enables Cross-Origin Resource Sharing for `http://localhost:5173` and `http://127.0.0.1:5173`.
  - **Pydantic Data Models**:
    - `AskRequest`: Validates `{ "doc_id": str, "question": str }`.
    - `AskResponse`: Formats `{ "answer": str, "sources": list[int] }`.
    - `UploadResponse`: Formats `{ "doc_id": str, "filename": str, "chunks": int }`.
  - **REST Endpoints**:
    - `GET /`: Returns API root status and documentation links.
    - `GET /api/health`: Returns service health, indexed document count, vector DB path, and active LLM providers.
    - `GET /api/documents`: Returns the list of all indexed documents with page and chunk metadata.
    - `DELETE /api/documents/{doc_id}`: Deletes a document's chunks from ChromaDB and registry.
    - `POST /api/upload`: Accepts `.pdf` or `.txt` file uploads, uses `asyncio.to_thread` to non-blockingly parse with PyMuPDF, chunk with `RecursiveCharacterTextSplitter (1000/200)`, embed, and store in ChromaDB.
    - `POST /api/ask`: Accepts question and `doc_id`, retrieves top 4 chunks via Hybrid RRF retrieval, passes to LLM with strict context-only prompt, and returns grounded answer with page numbers.

#### [`/backend/app/services/vector_store.py`](file:///e:/Task-RAG/backend/app/services/vector_store.py)
- **Role**: Core text extraction, document chunking, ChromaDB vector database interaction, and hybrid retrieval.
- **What is in this file**:
  - `VectorStoreService`: Class encapsulating all vector DB operations.
  - `extract_text_with_page_metadata()`:
    - Extracts PDF pages using **PyMuPDF** (`import fitz`) with layout-aware reading order (`sort=True`).
    - Detects and strips repetitive running headers and footers across pages to eliminate embedding noise.
    - Extracts TXT files and splits along explicit page/section headers (`Section X (Page Y)`), form feeds (`\x0c`), or logical pages.
    - Normalizes whitespace, strips control characters, and de-hyphenates words broken across line endings.
  - `index_document()`:
    - Splits text into chunks using `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`.
    - Enriches chunk text with unambiguous page contextual markers (`[Page X]`).
    - Inserts chunks into ChromaDB in safe batches of 200 chunks to prevent database parameter overflow on large documents.
    - Persists document metadata to `documents_registry.json`.
  - `_compute_keyword_score()`:
    - BM25-inspired lexical scorer that rewards exact phrase matches (+6.0), query term coverage (+4.0), exact numbers/percentages (+3.5), and technical acronyms (+3.0).
  - `retrieve_top_chunks()`:
    - **Hybrid RRF Search Engine**: Queries an expanded candidate pool (up to 32 chunks) from ChromaDB.
    - Merges dense vector distance and lexical score using Reciprocal Rank Fusion.
    - Applies near-duplicate chunk suppression (>75% token overlap) to ensure maximum context diversity.
    - Returns top 4 chunks, chunk metadata, and unique sorted source page numbers (`list[int]`).

#### [`/backend/app/services/llm_service.py`](file:///e:/Task-RAG/backend/app/services/llm_service.py)
- **Role**: Prompt synthesis, LLM client orchestration, and deterministic answer grounding.
- **What is in this file**:
  - `STRICT_CONTEXT_SYSTEM_PROMPT`: Rigid prompt instructing the LLM to rely strictly on provided excerpts, cite page numbers in `(Page X)` format, and return `"I cannot find the answer in the provided document context."` when unanswerable.
  - `format_context()`: Converts retrieved chunks into labeled excerpts: `[Excerpt N | Page X]: <chunk>`.
  - `generate_answer()`:
    - Multi-provider caller trying Google Gemini (`gemini-3.5-flash-lite`, `models/gemini-3.8-flash`) with deterministic `temperature=0.0`.
    - Secondary provider: OpenAI API (`gpt-4o-mini`) with `temperature=0.0`.
    - Built-in Grounded Fallback: Pure Python sentence-scoring extractor that operates 100% offline if API limits or network issues occur.

#### [`/backend/rag_service.py`](file:///e:/Task-RAG/backend/rag_service.py)
- **Role**: Self-contained RAG service module providing reference implementations and helper functions for text extraction, chunking, and ChromaDB queries.

#### [`/backend/requirements.txt`](file:///e:/Task-RAG/backend/requirements.txt)
- **Role**: Python dependency manifest.
- **Contents**:
  - `fastapi`: High-performance asynchronous REST API framework.
  - `uvicorn`: ASGI web server.
  - `pymupdf`: High-speed C-based PDF text and page extraction (`fitz`).
  - `chromadb`: Persistent local vector embedding database.
  - `langchain-text-splitters`: Sentence-aware character text splitting.
  - `google-genai`: Google Gemini generative AI SDK.
  - `openai`: OpenAI API client.
  - `python-dotenv`: Environment variable loader.
  - `pydantic`: Request/response validation schemas.

#### [`/backend/vector_db/`](file:///e:/Task-RAG/backend/vector_db/)
- **Role**: Persistent local on-disk vector database directory.
- **Contents**:
  - `chroma.sqlite3`: SQLite storage maintaining ChromaDB collections, chunk text, and metadata.
  - `documents_registry.json`: Registry tracking document IDs, original filenames, total chunks, page counts, and upload timestamps.
  - Subdirectories with UUIDs: Binary HNSW index files (`data_level0.bin`, `header.bin`, `length.bin`) used for nearest-neighbor vector similarity search.

---

### 3. Frontend Application (`/frontend`)

#### [`/frontend/index.html`](file:///e:/Task-RAG/frontend/index.html)
- **Role**: Single-page application HTML entrypoint.
- **Contents**: Sets page title, loads modern Google Fonts (`Plus Jakarta Sans`, `Inter`, `JetBrains Mono`), sets dark mode viewport defaults, and defines `<div id="root"></div>`.

#### [`/frontend/package.json`](file:///e:/Task-RAG/frontend/package.json)
- **Role**: Frontend package manifest and dependencies.
- **Contents**:
  - `react` & `react-dom` (v18): UI framework.
  - `lucide-react`: Icon library.
  - `axios`: HTTP client for REST requests.
  - `react-markdown`: Markdown rendering for LLM answers.
  - `tailwindcss`, `postcss`, `autoprefixer`: Utility-first styling pipeline.
  - `vite`: Fast build tool and development server.

#### [`/frontend/vite.config.js`](file:///e:/Task-RAG/frontend/vite.config.js)
- **Role**: Vite configuration.
- **Contents**: Configures the `@vitejs/plugin-react` plugin and local dev server settings.

#### [`/frontend/tailwind.config.js`](file:///e:/Task-RAG/frontend/tailwind.config.js)
- **Role**: Tailwind CSS styling configuration.
- **Contents**:
  - Custom color palette: Deep navy slate backgrounds (`#0a0f1d`), electric indigo/violet brand gradients (`#6366f1`, `#8b5cf6`).
  - Typography: Configures font families (`Plus Jakarta Sans`, `JetBrains Mono`).
  - Custom animations: `fade-in`, `slide-up`, `pulse-glow`.

#### [`/frontend/src/main.jsx`](file:///e:/Task-RAG/frontend/src/main.jsx)
- **Role**: React application bootstrap file.
- **Contents**: Imports `index.css` and mounts the root `<App />` component into the DOM.

#### [`/frontend/src/index.css`](file:///e:/Task-RAG/frontend/src/index.css)
- **Role**: Global stylesheet and design system tokens.
- **Contents**:
  - `@tailwind` directives for base, components, and utilities.
  - Custom glassmorphic utilities (`.glass-card`, `.glass-panel`).
  - Dark-mode styled scrollbars.
  - Gradient glow utilities and custom borders.

#### [`/frontend/src/App.jsx`](file:///e:/Task-RAG/frontend/src/App.jsx)
- **Role**: Master layout component.
- **Contents**:
  - Implements the split-screen design: Left sidebar (`FileUploader.jsx`) and right main panel (`ChatWindow.jsx`).
  - Top header navigation bar with system title, tech stack tags, and live backend health status indicator (`API Online` / `API Offline`).
  - Manages active document state (`activeDoc`, `activeDocId`) shared between upload sidebar and chat interface.

#### [`/frontend/src/components/FileUploader.jsx`](file:///e:/Task-RAG/frontend/src/components/FileUploader.jsx)
- **Role**: Left sidebar document upload and management component.
- **Contents**:
  - Drag-and-drop zone supporting `.pdf` and `.txt` files with visual drag states.
  - Upload execution posting `FormData` to `http://localhost:8000/api/upload`.
  - Dynamic upload progress bar and status text during PyMuPDF parsing and ChromaDB embedding.
  - Active document card highlighting current file, chunk count, and unique ID.
  - Indexed documents switcher list with file type badges and deletion button (`DELETE /api/documents/{doc_id}`).

#### [`/frontend/src/components/ChatWindow.jsx`](file:///e:/Task-RAG/frontend/src/components/ChatWindow.jsx)
- **Role**: Right panel chat interface and answer viewer.
- **Contents**:
  - Disabled overlay with padlock icon when no document is selected.
  - Sends user queries via Axios to `http://localhost:8000/api/ask`.
  - Renders markdown responses with syntax highlighting, lists, and formatted tables using `react-markdown`.
  - Renders clickable source page badges (`Page X`) under each response.
  - Clicking a source page badge triggers visual citation feedback and alerts the referenced page.
  - Suggested question chips for instant query exploration.
  - Auto-scrolls to the newest message upon response generation.
  - Automatically resets conversation history when switching active documents.

#### [`/frontend/src/api.js`](file:///e:/Task-RAG/frontend/src/api.js)
- **Role**: Centralized API service module.
- **Contents**: Exported Axios methods (`uploadFile()`, `askQuestion()`, `getDocuments()`, `deleteDocument()`, `checkHealth()`) pointing to backend base URL `http://localhost:8000`.

#### Supplementary Components:
- [`/frontend/src/components/Navbar.jsx`](file:///e:/Task-RAG/frontend/src/components/Navbar.jsx): Navigation bar component.
- [`/frontend/src/components/ChatArea.jsx`](file:///e:/Task-RAG/frontend/src/components/ChatArea.jsx): Reusable message thread component.
- [`/frontend/src/components/DocumentSidebar.jsx`](file:///e:/Task-RAG/frontend/src/components/DocumentSidebar.jsx): Collapsible document list component.
- [`/frontend/src/components/UploadModal.jsx`](file:///e:/Task-RAG/frontend/src/components/UploadModal.jsx): Pop-up upload modal component.

---

### 4. Test Documents (`/test_docs`)

#### [`/test_docs/sample_quantum_computing.txt`](file:///e:/Task-RAG/test_docs/sample_quantum_computing.txt)
- **Role**: Test TXT document for validating section-based parsing, keyword scoring, and numerical accuracy.
- **Contents**: 4 sections detailing Quantum Volume (262,144), Algorithms (VQE, QAOA), Cryogenic specifications (14.2 mK), and Fault Tolerance roadmaps (0.05% error threshold).

#### [`/test_docs/sample_ai_report.pdf`](file:///e:/Task-RAG/test_docs/sample_ai_report.pdf)
- **Role**: Test PDF document for validating PyMuPDF page extraction, multi-page citations, and table extraction.

---

## Complete API Contracts

### 1. Document Upload
- **Method / Path**: `POST /api/upload`
- **Request Body**: `multipart/form-data` with `file: UploadFile` (.pdf or .txt)
- **Response Format**:
```json
{
  "doc_id": "70f1956c-0720-4c63-9974-bbd5dbe3c0a2",
  "filename": "quantum_report.pdf",
  "chunks": 25
}
```

### 2. Document Question-Answering
- **Method / Path**: `POST /api/ask`
- **Request Body**: `application/json`
```json
{
  "doc_id": "70f1956c-0720-4c63-9974-bbd5dbe3c0a2",
  "question": "What is the base plate temperature of the dilution refrigerator?"
}
```
- **Response Format**:
```json
{
  "answer": "The base plate temperature of the dilution refrigerator is 14.2 millikelvin (Page 3).",
  "sources": [3]
}
```
- **Unanswerable Query Response**:
```json
{
  "answer": "I cannot find the answer in the provided document context.",
  "sources": []
}
```
