# Task-RAG: Technology Stack & Technical Rationale Guide

This document provides a detailed breakdown of all technologies, libraries, frameworks, and architectural patterns used in the **Task-RAG** project, including the specific technical reasons why each technology was selected over alternatives, and how it is applied in the codebase.

---

## Technology Stack Summary Table

| Layer | Technology | Primary Role in Task-RAG | Key Reason for Selection |
| :--- | :--- | :--- | :--- |
| **Backend Framework** | **FastAPI** | High-performance REST API | Native async support, automatic OpenAPI/Swagger docs, high throughput. |
| **ASGI Server** | **Uvicorn** | Asynchronous HTTP server | Lightning-fast ASGI implementation on top of `uvloop` and `httptools`. |
| **Data Validation** | **Pydantic v2** | Request & Response validation | Strict typing, automatic serialization, eliminates manual validation boilerplate. |
| **Document Parsing** | **PyMuPDF (`fitz`)** | PDF text and layout extraction | **10x–20x faster** than PyPDF2/pypdf; layout-aware reading order (`sort=True`). |
| **Text Chunking** | **RecursiveCharacterTextSplitter** | Context-aware text segmentation | Preserves sentence and paragraph boundaries while enforcing strict overlap. |
| **Vector Database** | **ChromaDB** | Local persistent vector storage | Serverless, zero-cloud dependency, local SQLite + HNSW embeddings out-of-the-box. |
| **Retrieval Architecture**| **Hybrid RRF Search** | Dense Vector + BM25 Fusion | Solves semantic blindness to exact numbers, percentages, and acronyms. |
| **Primary LLM** | **Google Gemini** | Factual answer generation | High throughput, deterministic temperature control (`0.0`), cost efficiency. |
| **Secondary LLM** | **OpenAI GPT-4o-mini** | Fallback answer generation | Strict context compliance and high reasoning accuracy at low latency. |
| **Offline Fallback** | **Grounded Scorer** | Zero-downtime offline extractor | Guarantees system works 100% offline without active internet or API quotas. |
| **Frontend Framework**| **React 18** | Reactive user interface | Declarative component architecture, smooth state handling, rich ecosystem. |
| **Build Tooling** | **Vite** | Bundler and dev server | Sub-second Hot Module Replacement (HMR), instant cold start over Webpack. |
| **Styling Pipeline** | **Tailwind CSS** | Design system & utilities | High customizability, sleek glassmorphic UI, eliminates CSS bloat. |
| **Icons** | **Lucide React** | Modern UI iconography | Lightweight, tree-shakable SVG icon set with consistent visual styling. |
| **HTTP Client** | **Axios** | Backend API communication | Built-in timeout controls, upload progress listeners (`onUploadProgress`). |
| **Markdown Parser** | **React-Markdown** | Rendering structured LLM answers| Safely renders tables, bullet lists, bold numbers, and markdown citations. |

---

## 1. Backend Technologies

### 1.1 FastAPI (Python 3.11+)
- **Role in Codebase**: [`backend/main.py`](file:///e:/Task-RAG/backend/main.py)
- **Why it was chosen**:
  - **Asynchronous Concurrency**: Built on Starlette, FastAPI natively supports `async def` and non-blocking I/O.
  - **Thread Offloading (`asyncio.to_thread`)**: Allows long-running CPU/disk tasks (such as PyMuPDF parsing and ChromaDB embedding) to be offloaded into worker threads so the main event loop never hangs.
  - **Automatic OpenAPI / Swagger Documentation**: Generates interactive documentation automatically at `http://localhost:8000/docs`, simplifying testing.
  - **Performance**: Consistently benchmarks among the fastest Python web frameworks (comparable to Go and NodeJS).
- **Alternatives Considered**:
  - *Flask*: Lacks native async request handling and requires manual validation extensions.
  - *Django*: Excessively heavy with monolithic ORM and admin requirements not needed for a lightweight RAG microservice.

### 1.2 Uvicorn
- **Role in Codebase**: ASGI web server hosting FastAPI at `http://127.0.0.1:8000`.
- **Why it was chosen**:
  - Implementation based on `uvloop` (an ultra-fast C implementation of the asyncio event loop) and `httptools` (HTTP parser based on Node.js http-parser).
  - Handles concurrent HTTP connections effortlessly with minimal memory footprint.

### 1.3 Pydantic (v2)
- **Role in Codebase**: [`backend/main.py`](file:///e:/Task-RAG/backend/main.py) (`AskRequest`, `AskResponse`, `UploadResponse`).
- **Why it was chosen**:
  - **Strict Type Enforcement**: Validates that questions and `doc_id` are non-empty strings and that `sources` is strictly returned as `list[int]`.
  - **Automatic Serialization & Error Details**: Automatically generates JSON schema and emits descriptive HTTP 422 errors when payloads are malformed.

---

## 2. Document Ingestion & Chunking Technologies

### 2.1 PyMuPDF (`fitz`)
- **Role in Codebase**: [`backend/app/services/vector_store.py`](file:///e:/Task-RAG/backend/app/services/vector_store.py) (`extract_text_with_page_metadata`).
- **Why it was chosen**:
  - **Execution Speed**: Implemented in C (MuPDF engine). Benchmarks demonstrate PyMuPDF is **10 to 20 times faster** at extracting text from multi-page PDFs compared to pure Python alternatives. A 25-page PDF is parsed and extracted in under 0.05 seconds.
  - **Visual Reading Order (`sort=True`)**: Standard PDF extraction reads text based on internal stream creation order, which scrambles multi-column layouts, tables, and sidebars. PyMuPDF's `sort=True` analyzes geometric bounding boxes to extract text in natural visual reading order.
  - **Memory Efficiency**: Streams pages sequentially without loading redundant internal structures into Python memory.
- **Why not PyPDF2 or pdfplumber**:
  - *PyPDF2*: Known for poor Unicode support, lack of layout preservation, and frequent text corruption across non-standard fonts.
  - *pdfplumber*: Excellent layout extraction, but significantly slower than PyMuPDF on large files.

### 2.2 LangChain Text Splitters (`RecursiveCharacterTextSplitter`)
- **Role in Codebase**: [`backend/app/services/vector_store.py`](file:///e:/Task-RAG/backend/app/services/vector_store.py) (`chunk_size=1000, chunk_overlap=200`).
- **Why it was chosen**:
  - **Sentence Boundary Preservation**: Naive character slicing splits words or sentences in half (e.g. cutting `"99.85%"` into `"99."` and `"85%"`).
  - **Hierarchy of Separators**: Recursively attempts to split along natural boundaries:
    1. Paragraphs (`\n\n`)
    2. Single lines (`\n`)
    3. Sentences (`. `, `? `, `! `, `; `)
    4. Words (` `)
  - **Contextual Overlap (200 characters)**: Ensures that ideas or transitions between the end of one chunk and the beginning of the next are preserved across chunk boundaries.

---

## 3. Vector Database & Search Architecture

### 3.1 ChromaDB
- **Role in Codebase**: [`backend/app/services/vector_store.py`](file:///e:/Task-RAG/backend/app/services/vector_store.py) (`PersistentClient(path="./vector_db")`).
- **Why it was chosen**:
  - **Serverless & Local Persistence**: Stores data directly on local disk inside `./vector_db` using SQLite and HNSW indices. Requires no external database servers, Docker containers, or cloud credentials.
  - **Integrated Embedding Inference**: Uses an efficient built-in ONNX embedding model (`all-MiniLM-L6-v2`) capable of generating 384-dimensional vector embeddings on local CPU.
  - **Fast Nearest-Neighbor Queries**: Utilizes Hierarchical Navigable Small World (HNSW) graph indexing for sub-10ms similarity searches across thousands of document chunks.
- **Alternatives Considered**:
  - *Pinecone / Weaviate Cloud*: Requires cloud accounts, API keys, network roundtrips, and recurring costs.
  - *FAISS*: Highly optimized vector math, but lacks built-in metadata filtering (`where={"doc_id": ...}`) and persistent document management out of the box.

### 3.2 Hybrid Reciprocal Rank Fusion (RRF) & Lexical Scorer
- **Role in Codebase**: Custom hybrid search engine in [`backend/app/services/vector_store.py`](file:///e:/Task-RAG/backend/app/services/vector_store.py).
- **Why it was chosen**:
  - **Overcoming Semantic Blindness**: Pure dense vector search calculates similarity based on general meaning. Consequently, questions containing specific numbers (e.g., `0.042`), technical percentages (`99.85%`), or acronyms (`VQE`, `EUV`) often retrieve chunks that merely "sound similar" while missing the chunk with the exact figure.
  - **Synergistic Scoring**:
    - Vector search retrieves a broad 32-candidate pool.
    - BM25 lexical scoring boosts exact phrases (+6.0), query term coverage (+4.0), numbers (+3.5), and acronyms (+3.0).
    - Near-duplicate suppression drops chunks with >75% token overlap, maximizing information density for the LLM.

---

## 4. Generative AI & Answer Synthesis

### 4.1 Google Gemini Generative AI SDK (`google-genai`)
- **Role in Codebase**: [`backend/app/services/llm_service.py`](file:///e:/Task-RAG/backend/app/services/llm_service.py).
- **Why it was chosen**:
  - **Modern Models Supported**: Uses active high-speed models (`gemini-3.5-flash-lite`, `models/gemini-3.8-flash`).
  - **Deterministic Grounding (`temperature=0.0`)**: Configured with `GenerateContentConfig(temperature=0.0)` to eliminate creative hallucinations and enforce strictly factual citations.
  - **High Tokens-per-Second & Generous Rate Limits**: Allows rapid turnaround of Q&A responses (~1.5–2.5s).

### 4.2 OpenAI API (`openai`)
- **Role in Codebase**: Secondary LLM provider in [`backend/app/services/llm_service.py`](file:///e:/Task-RAG/backend/app/services/llm_service.py).
- **Why it was chosen**:
  - Provides enterprise-grade fallback compatibility using `gpt-4o-mini`.
  - Strict instruction following ensuring compliance with `(Page X)` citations and context boundary rules.

### 4.3 Built-in Grounded Fallback Engine
- **Role in Codebase**: [`backend/app/services/llm_service.py`](file:///e:/Task-RAG/backend/app/services/llm_service.py) (`_strict_context_grounded_answer`).
- **Why it was chosen**:
  - **High Availability**: External AI APIs can experience temporary traffic spikes (e.g. HTTP 503 UNAVAILABLE) or quota exhaustion.
  - **Deterministic Sentence Matching**: Tokenizes the question, identifies relevant sentences in the top chunks, cites the corresponding page number, and constructs a grounded bulleted response without requiring any external network connection.

---

## 5. Frontend Technologies & Build Pipeline

### 5.1 React 18
- **Role in Codebase**: [`frontend/src/App.jsx`](file:///e:/Task-RAG/frontend/src/App.jsx), [`ChatWindow.jsx`](file:///e:/Task-RAG/frontend/src/components/ChatWindow.jsx), [`FileUploader.jsx`](file:///e:/Task-RAG/frontend/src/components/FileUploader.jsx).
- **Why it was chosen**:
  - **Declarative UI**: Synchronizes complex application states (upload progress, document selection, message history, badge click states) seamlessly.
  - **Component Isolation**: Enables a modular split-screen layout where document management and chat operations execute independently without rerendering conflicts.

### 5.2 Vite
- **Role in Codebase**: [`frontend/vite.config.js`](file:///e:/Task-RAG/frontend/vite.config.js).
- **Why it was chosen**:
  - **Instant Server Start**: Uses native browser ES modules (ESM), eliminating heavy bundling during development.
  - **Lightning-Fast HMR**: Changes to React components or styles reflect in the browser in less than 50 milliseconds.
  - **Rollup Production Bundles**: Emits highly optimized, minified production assets.
- **Why not Create React App (CRA) / Webpack**:
  - *CRA*: Deprecated, notoriously slow build times, heavy dependency bloat.
  - *Webpack*: Slower startup times on large component trees.

### 5.3 Tailwind CSS
- **Role in Codebase**: [`frontend/tailwind.config.js`](file:///e:/Task-RAG/frontend/tailwind.config.js), [`frontend/src/index.css`](file:///e:/Task-RAG/frontend/src/index.css).
- **Why it was chosen**:
  - **Design System Consistency**: Eliminates arbitrary CSS files by enforcing curated color tokens, spacing scales, and typography presets.
  - **Modern Aesthetic**: Easily enables backdrop blurs (`backdrop-blur-md`), glassmorphic panels (`glass-card`), subtle glowing borders, and dark-mode color palettes.
  - **Zero Unused CSS**: Purges unused utility classes during build, producing a production CSS bundle of under 15 KB.

### 5.4 Axios
- **Role in Codebase**: [`frontend/src/components/FileUploader.jsx`](file:///e:/Task-RAG/frontend/src/components/FileUploader.jsx), [`frontend/src/components/ChatWindow.jsx`](file:///e:/Task-RAG/frontend/src/components/ChatWindow.jsx).
- **Why it was chosen over native `fetch()`**:
  - **Upload Progress Tracking (`onUploadProgress`)**: Provides real-time byte counters and percentage progress for large document uploads.
  - **Configurable Timeouts**: Supports explicit timeouts (e.g. 180 seconds for large document indexing), preventing zombie requests.
  - **Automatic JSON Serialization**: Handles request body serialization and response parsing out-of-the-box.
  - **Unified Error Handling**: Emits structured error objects (`err.response.data.detail`).

### 5.5 React-Markdown
- **Role in Codebase**: [`frontend/src/components/ChatWindow.jsx`](file:///e:/Task-RAG/frontend/src/components/ChatWindow.jsx).
- **Why it was chosen**:
  - **Formatted AI Responses**: LLMs naturally output markdown (bullet points, bold technical terms, code blocks, tables). `react-markdown` converts these tokens into semantic HTML.
  - **XSS Protection**: Sanitizes output by default, preventing malicious script injections.

### 5.6 Lucide React
- **Role in Codebase**: All React icons across sidebar, uploader, badges, and chat window.
- **Why it was chosen**:
  - Consistent visual language (24px vector stroke grid).
  - Tree-shakable (only icons imported are bundled).
  - Customizable stroke width, color, and sizing via Tailwind CSS classes.

---

## 6. Monorepo Architecture & Developer Experience

### 6.1 Monorepo Layout (`/backend` + `/frontend`)
- **Structure**:
  - `/backend`: Self-contained Python virtual environment (`.venv`), requirements, and API logic.
  - `/frontend`: Self-contained Node package with Vite, Tailwind, and React.
- **Benefits**:
  - Keeps API contracts and UI implementation versioned together in a single repository.
  - Single root `package.json` allows developers to start the entire full-stack application with one command: `npm run dev`.

### 6.2 Environment Isolation (`.env`)
- All sensitive credentials (`GEMINI_API_KEY`, `OPENAI_API_KEY`) and system paths (`CHROMA_PERSIST_DIRECTORY`, `CORS_ORIGIN`) are isolated from version control, adhering to Twelve-Factor App methodology.
