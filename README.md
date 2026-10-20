# File-Summariser.Ai

Full-stack Document Question-Answering and Summarization system powered by **FastAPI**, **PyMuPDF**, **ChromaDB**, **React (Vite)**, and **Google Gemini / OpenAI LLMs**.

---

## Key Capabilities

- **Multi-Format Ingestion**: Ingests **PDF**, **Microsoft Word (.docx, .doc)**, and **Plain Text (.txt, .md)** with layout-aware visual reading order.
- **High-Speed Hybrid RRF Search**: Direct ChromaDB vector retrieval fused with BM25 lexical keyword, numerical, and acronym scoring via Reciprocal Rank Fusion (RRF).
- **Multi-Document Question Synthesis**: Reads across **all uploaded files** simultaneously on the main page to generate relevant questions representing each document and comparative themes.
- **Physical Page Citations & In-App Viewer**: Interactive source badges (`Page X`) jump directly to the exact physical page of the source document in a browser tab or in-app modal.
- **Persistent Conversation Storage**: SQLite conversation threads preserved per document with full message history and "Clear Chat" controls.
- **High-Speed LLM Engine**: Cached Google Gemini (`gemini-3.5-flash-lite`, `gemini-flash-lite-latest`) and OpenAI (`gpt-4o-mini`) client sessions with zero-hallucination deterministic grounding.

---

## Documentation Guides

- **[Visual Architecture & Process Guide](file:///e:/Task-RAG/PROJECT_VISUAL_GUIDE.md)**: Visual sequence diagrams, flowcharts, state machines, and data pipelines for every process in the project.
- **[System Processes & Lifecycle Guide](file:///e:/Task-RAG/PROJECT_PROCESSES.md)**: Technical breakdown of ingestion, chunking, hybrid retrieval, and multi-file question synthesis.
- **[Project Documentation](file:///e:/Task-RAG/PROJECT_DOCUMENTATION.md)**: Complete file-by-file directory reference, API specifications, and setup instructions.
- **[Technologies & Libraries](file:///e:/Task-RAG/PROJECT_TECHNOLOGIES.md)**: Full technology stack, architecture rationale, and test suite details.
- **[Changelog & Milestones](file:///e:/Task-RAG/PROJECT_CHANGELOG.md)**: Complete log of features, milestones, and architectural updates.

---

## Quick Start

```bash
# Install dependencies
npm install

# Run both backend and frontend concurrently
npm run dev
# or
npm start
```

- **Frontend Application**: [http://localhost:5173](http://localhost:5173)
- **FastAPI Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Automated Test Suite

Run the full 8-phase test suite (Health, Documents, Page Detail, File Stream, Suggested Questions, Single-Doc Ask, Multi-Doc Ask, and Chat History):

```powershell
backend\.venv\Scripts\python.exe backend/test_full_suite.py
```
*(All 8 test phases complete in ~5.8 seconds)*