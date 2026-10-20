# File Summariser.Ai — Comprehensive Visual Process Guide

This document provides visual diagrams and architectural flowcharts for all end-to-end processes operating inside the **File Summariser.Ai** RAG platform.

---

## 1. High-Level System Architecture & Component Topology

```mermaid
flowchart TB
    subgraph Client["Frontend Layer (React 18 + Vite + Tailwind CSS)"]
        UI["Main Split-Screen Workspace"]
        UploadComp["FileUploader & Dropzone"]
        ChatComp["ChatWindow & ChatArea"]
        ModalComp["DocumentPageModal Viewer"]
        StateStore["Client State (Doc ID, Messages, Suggestions)"]
    end

    subgraph API["FastAPI Gateway (Uvicorn :8000)"]
        Endpoints["REST Controllers<br/>/api/upload | /api/ask | /api/documents<br/>/api/sequential-questions"]
        CORS["CORS Middleware (Origins: 5173)"]
        AsyncLoop["Asyncio Thread Pool Executor"]
    end

    subgraph IngestionEngine["Document Processing & Vector Engine"]
        Parser["PyMuPDF / python-docx Parsers"]
        Splitter["RecursiveCharacterTextSplitter<br/>(chunk_size=1000, overlap=200)"]
        ChromaStore[("ChromaDB Vector Store<br/>./vector_db")]
        Registry[("documents_registry.json")]
    end

    subgraph Inference["LLM Reasoning & Generation Engine"]
        LLMRouter["LLMService Controller"]
        GeminiFlash["Google Gemini API<br/>(gemini-3.1-flash-lite / gemini-3.5-flash)"]
        OpenAIGPT["OpenAI API Fallback<br/>(gpt-4o-mini)"]
        OfflineHeuristic["Deterministic Heuristic Fallback Engine<br/>(100% Offline)"]
    end

    subgraph Persistence["Dual-Tier Chat & File Persistence"]
        SQLiteDB[("Local SQLite Database<br/>chat_history.db")]
        FirebaseFirestore[("Google Firebase Firestore<br/>(documents/{docId}/messages)")]
        FirebaseStorage[("Firebase Cloud Storage Bucket<br/>(gs://documents/{docId})")]
    end

    %% Connections
    UI --> UploadComp & ChatComp & ModalComp
    UploadComp -->|POST /api/upload| Endpoints
    ChatComp -->|POST /api/ask| Endpoints
    ChatComp -->|GET /api/documents/:id/chat| Endpoints
    ModalComp -->|GET /api/documents/:id/pages/:num| Endpoints

    Endpoints --> CORS --> AsyncLoop
    AsyncLoop --> Parser --> Splitter --> ChromaStore
    AsyncLoop --> Registry
    AsyncLoop --> LLMRouter

    LLMRouter --> GeminiFlash
    LLMRouter -->|Fallback| OpenAIGPT
    LLMRouter -->|Offline / Error| OfflineHeuristic

    AsyncLoop --> SQLiteDB
    AsyncLoop --> FirebaseFirestore & FirebaseStorage
```

---

## 2. Document Upload & Ingestion Pipeline

When a user uploads a document, the backend parses text, constructs page-aware chunk metadata, embeds chunks in ChromaDB, and pre-generates document suggestions.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as React Frontend
    participant API as FastAPI (/api/upload)
    participant Parser as File Parsers (PyMuPDF / docx)
    participant Splitter as Text Splitter
    participant Chroma as ChromaDB
    participant LLM as LLM Engine
    participant Cloud as Firebase & Registry

    User->>Frontend: Drag & drop file (.pdf, .docx, .txt)
    Frontend->>API: POST /api/upload (FormData)
    API->>Parser: Extract text per page
    
    alt File is .pdf
        Parser->>Parser: PyMuPDF fitz layout sorting & header/footer strip
    else File is .docx
        Parser->>Parser: python-docx paragraphs + tables extraction
    else File is .txt / .md
        Parser->>Parser: UTF-8 decode & virtual 2500-char page slicing
    end

    Parser-->>API: Pages list with text & page numbers
    API->>Splitter: Split into 1000-char chunks with 200-char overlap
    Splitter-->>API: Chunks with [Page X] tags & metadata

    API->>Chroma: Add embeddings in batches of 200
    Chroma-->>API: Stored in Chroma persistent collection

    API->>LLM: Generate 3-4 file-tailored initial questions
    LLM-->>API: Return JSON array of questions
    
    API->>Cloud: Update registry & sync to Firebase Storage/Firestore
    API-->>Frontend: { doc_id, filename, chunks, suggested_questions }
    Frontend-->>User: Update sidebar list, select doc, show suggested questions
```

---

## 3. Hybrid RRF Retrieval & Question-Answering Pipeline

The system retrieves the top semantic chunks using ChromaDB vector search and blends them with BM25 lexical ranking before passing them to the LLM with a strict context-only prompt.

```mermaid
flowchart TD
    Q[User Submits Question] --> Lock[Frontend Sets isAnswering=true]
    Lock --> APIReq[POST /api/ask<br/>doc_id, question]
    
    APIReq --> StoreUserQ[Persist User Question to SQLite & Firestore]
    StoreUserQ --> QueryVec[Vector Embed Query in ChromaDB]

    subgraph HybridEngine["Hybrid Search Engine"]
        QueryVec --> DenseSearch[Dense Vector Similarity Search<br/>Retrieve Top Candidates]
        QueryVec --> BM25Search[BM25 Lexical Keyword Search<br/>Token Matching]
        DenseSearch & BM25Search --> RRF[Reciprocal Rank Fusion RRF Scoring<br/>Score = 1 / 60 + Rank]
        RRF --> SelectTop4[Filter Top 4 Most Relevant Chunks]
    end

    SelectTop4 --> HasChunks{Chunks Retrieved?}
    
    HasChunks -->|No| FallbackRefusal[Return Context Refusal & Guidance]
    HasChunks -->|Yes| PromptSynth[Construct Strict Context Prompt<br/>Embed Top 4 Chunks with Page Labels]

    subgraph LLMInference["LLM Generation"]
        PromptSynth --> TryGemini[Google Gemini Flash API]
        TryGemini -->|Spike/Fail| TryOpenAI[OpenAI gpt-4o-mini]
        TryOpenAI -->|Fail/Offline| OfflineSynth[Heuristic Sentence Extractor]
    end

    TryGemini & TryOpenAI & OfflineSynth --> ExtractCitations[Regex Extract Page Citations: Page X]
    ExtractCitations --> GenSequential[Generate 3 Sequential Follow-up Questions]
    GenSequential --> PersistAssistant[Persist Answer, Sources, and Sequential Questions]
    PersistAssistant --> ReturnRes[Return AskResponse to Frontend]

    ReturnRes --> RenderUI[Render Answer Markdown + Clickable Source Badges + Sequential Question Chips]
    RenderUI --> Unlock[Frontend Sets isAnswering=false]
```

---

## 4. Sequential Question Suggestion Flow (Follow-Up Generator)

After answering a question, the LLM generates 3 sequential follow-up questions relevant to both the document and the preceding Q&A exchange.

```mermaid
sequenceDiagram
    autonumber
    participant UI as Chat Window
    participant API as Backend (/api/ask)
    participant Store as Vector Store & Registry
    participant LLM as LLMService
    participant DB as SQLite & Firebase

    UI->>API: User asks: "What AWS services were used?"
    API->>Store: Retrieve chunks + doc metadata
    API->>LLM: generate_answer(question, chunks)
    LLM-->>API: Returns answer with page citations
    
    Note over API, LLM: Sequential Question Suggestion Phase
    API->>LLM: generate_sequential_questions(filename, question, answer, chunks)
    
    rect rgb(20, 30, 50)
        Note over LLM: LLM analyzes:<br/>1. Document subject & excerpts<br/>2. Previous question<br/>3. Generated answer facts & entities
        LLM->>LLM: Formulate 3 progressive logical follow-ups (JSON array)
    end
    
    alt LLM API Available
        LLM-->>API: ["How was Lambda connected to S3?", "What IAM policies were used?", "What deployment pipeline was configured?"]
    else API Timeout / Offline
        LLM->>LLM: _generate_heuristic_sequential_questions (entity keyword extractor)
        LLM-->>API: 3 entity-grounded fallback questions
    end

    API->>DB: Save assistant message + sources + suggested_questions
    API-->>UI: AskResponse { answer, sources, suggested_questions }
    
    UI-->>UI: Display Answer Card
    UI-->>UI: Render "Suggested Follow-up Questions" interactive cards
    UI-->>UI: Update "Next:" quick-action chips above input bar
    
    Note over UI: User clicks a follow-up chip -> Instant next question!
```

---

## 5. Dual-Tier Storage & Persistence Lifecycle

Conversations and indexed files are persisted locally in SQLite and synchronized with Firebase Firestore and Firebase Storage.

```mermaid
flowchart LR
    subgraph Frontend["React Application"]
        ChatState["Chat Messages State"]
    end

    subgraph BackendAPI["FastAPI Backend Services"]
        ChatHistory["ChatHistoryService"]
        VectorStore["VectorStoreService"]
        FirebaseService["FirebaseService"]
    end

    subgraph LocalStorage["Local Persistent Tier"]
        SQLite[("SQLite DB<br/>chat_history.db<br/>- id<br/>- doc_id<br/>- role<br/>- content<br/>- sources<br/>- suggested_questions<br/>- timestamp")]
        ChromaLocal[("ChromaDB Files<br/>vector_db/chroma.sqlite3")]
        DocRegistry[("documents_registry.json")]
        RawFiles[("vector_db/files/*.*")]
    end

    subgraph CloudStorage["Cloud Firebase Tier (Optional)"]
        Firestore[("Firestore Collection<br/>documents/{doc_id}/messages")]
        CloudBucket[("Cloud Storage Bucket<br/>gs://documents/{doc_id}")]
    end

    ChatState <-->|Read / Write| BackendAPI
    BackendAPI <-->|Primary Read/Write| SQLite
    BackendAPI <-->|Embeddings & Docs| ChromaLocal & DocRegistry & RawFiles
    BackendAPI -.->|Real-time Sync| Firestore
    BackendAPI -.->|Backup Archive| CloudBucket
```

---

## 6. Frontend Split-Screen State Machine

```mermaid
stateDiagram-v2
    [*] --> Idle: App Mounts

    state Idle {
        [*] --> CheckBackendHealth
        CheckBackendHealth --> LoadDocList: Health OK
        LoadDocList --> SelectFirstDoc: Docs Found
        LoadDocList --> EmptyState: No Docs Found
    }

    state DocumentSelected {
        [*] --> FetchChatHistory
        FetchChatHistory --> RenderChat: History Found
        FetchChatHistory --> FetchInitialSuggestions: No History
        FetchInitialSuggestions --> RenderEmptyChatWithPrompts
    }

    state AnsweringQuestion {
        LockSidebar: Disable File Switching
        LockInput: Disable Ask Button & Input
        ShowBotSpinner: Render Querying ChromaDB Animation
    }

    state PageInspection {
        OpenModal: DocumentPageModal Opened
        LoadPageText: GET /api/documents/:id/pages/:num
        ServeDirectFile: Inline File Viewer #page=X
    }

    Idle --> DocumentSelected: User Selects File
    DocumentSelected --> AnsweringQuestion: User Submits Question / Clicks Suggestion
    AnsweringQuestion --> DocumentSelected: AskResponse Received (Answer + Sequential Qs)
    DocumentSelected --> PageInspection: User Clicks Source Page Badge
    PageInspection --> DocumentSelected: User Closes Modal
```

---

## 7. In-App Document Page Viewer Modal Flow

When a user clicks on any source citation badge `(Page X)` in an assistant answer, the in-app modal opens directly to that page:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Chat as Chat Message Badge
    participant Modal as DocumentPageModal
    participant API as FastAPI Backend
    participant Fitz as PyMuPDF Reader

    User->>Chat: Click "Page 2" citation badge
    Chat->>Modal: Open modal (docId, page=2)
    Modal->>API: GET /api/documents/{docId}/pages/2
    API->>Fitz: Extract text and logical bounds for page 2
    Fitz-->>API: Page text + total page count + filename
    API-->>Modal: { page: 2, total_pages: 8, content: "...", filename: "..." }
    Modal-->>User: Render text view with page navigation (Prev / Next)
    
    opt Open Original File
        User->>Modal: Click "Open PDF Viewer"
        Modal->>API: GET /api/documents/{docId}/file#page=2
        API-->>User: Stream original file with inline disposition
    end
```

---

## Summary of Core API Contracts

| Endpoint | Method | Input Payload | Output Payload | Primary Engine |
| :--- | :--- | :--- | :--- | :--- |
| `/api/upload` | `POST` | `multipart/form-data (file)` | `{ doc_id, filename, chunks, suggested_questions }` | PyMuPDF / python-docx + ChromaDB + LLM |
| `/api/ask` | `POST` | `{ doc_id, question }` | `{ answer, sources: int[], suggested_questions: string[] }` | Hybrid RRF + LLM + Citations + Sequential Engine |
| `/api/documents/{id}/sequential-questions` | `POST` | `{ doc_id, question, answer? }` | `{ sequential_questions: string[] }` | LLM Sequential Follow-up Engine |
| `/api/documents/{id}/chat` | `GET` | `doc_id (path)` | `{ doc_id, messages: Message[] }` | SQLite / Firestore Chat Persistence |
| `/api/documents/{id}/chat` | `DELETE`| `doc_id (path)` | `{ doc_id, status: "cleared" }` | SQLite / Firestore Chat Reset |
| `/api/documents/{id}/pages/{num}` | `GET` | `doc_id, num (path)` | `{ page, total_pages, content, filename }` | PyMuPDF Text Slicer |
| `/api/documents/{id}/file` | `GET` | `doc_id (path)` | File binary (`application/pdf`, etc.) | Direct FileResponse Stream with `#page=X` |
