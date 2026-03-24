# Sales MAS — Multi-Agent System for Sales & Marketing

A production-grade multi-agent system that automatically scores and ranks B2B sales prospects using parallel Celery agents, LangGraph orchestration, dual-modal RAG (text + OCR), and Groq Llama 3 8B.

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# 2. Start everything
make start

# 3. Open
#   Streamlit UI   → http://localhost:8501
#   API Swagger    → http://localhost:8000/docs
#   Flower monitor → http://localhost:5555
```

## Architecture

```
Event (lead/email/demo)
    │
    ▼
FastAPI (async, non-blocking)
    │
    ▼
Celery Group (5 parallel agents)
    ├── firmographic_agent
    ├── intent_agent
    ├── engagement_agent
    ├── social_agent
    └── historical_agent
    │
    ▼ (all results merged)
LangGraph Graph
    aggregate → rag_enrich → score → route
                                       ├── rep_notify   (≥70)
                                       ├── human_review (55–65)
                                       ├── nurture      (40–69)
                                       └── deprioritize (<40)
    │
    ▼
Chroma Vector Store (dual: text + OCR)
    ├── Text pipeline  — PDFs, JSON, CSV, TXT
    └── OCR pipeline   — Images, scanned PDFs (Tesseract)
```

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI (fully async) |
| Agent orchestration | LangGraph |
| Concurrency | Celery + Redis |
| Vector store | Chroma (2 collections) |
| OCR | Tesseract via pytesseract |
| LLM | Groq — Llama 3 8B (`llama3-8b-8192`) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Frontend | Streamlit |
| Task monitoring | Flower |

## Services

| Service | Port | Description |
|---|---|---|
| Streamlit | 8501 | Main dashboard UI |
| FastAPI | 8000 | REST API + Swagger docs |
| Flower | 5555 | Celery task monitor |
| Redis | 6379 | Message broker + result backend |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/prospects/ingest` | Ingest event (async, non-blocking) |
| POST | `/prospects/score/sync` | Score prospect (synchronous) |
| GET | `/prospects` | List all scored prospects (ranked) |
| GET | `/prospects/{id}` | Get prospect detail |
| POST | `/documents/upload` | Upload doc for RAG indexing |
| POST | `/feedback` | Record deal outcome |
| GET | `/review/queue` | Get borderline prospects pending review |
| POST | `/review/decide` | Submit human review decision |
| GET | `/stats` | Pipeline statistics |

## LangGraph Design

The graph has 4 sequential nodes then conditional fan-out:

1. **aggregate** — validates and normalises signals from Celery workers. If an agent failed, its slot is filled with a zero-strength placeholder so the pipeline continues.
2. **rag_enrich** — queries both Chroma collections (text + OCR) using the prospect's company/industry as the query. Returns combined context.
3. **score** — calls Groq Llama 3 8B with signals + RAG context. Returns score 0–100, grade A–D, rationale, recommended action.
4. **route** — conditional edge: `≥70 → rep_notify`, `55–65 → human_review`, `40–69 → nurture`, `<40 → deprioritize`.

## Celery Design

All 5 signal agents fire simultaneously using `celery.group()`. Each agent has:
- `max_retries=2` with exponential backoff
- `soft_time_limit=30s` to prevent hanging
- Graceful failure: if one agent times out, others complete normally

Results are aggregated and a composite score is computed before passing to LangGraph.

## RAG Pipeline

Documents are routed at ingest time:
- **Text pipeline**: reads raw text, splits into 500-char chunks, embeds via sentence-transformers, stores in `text_documents` Chroma collection
- **OCR pipeline**: runs Tesseract OCR, then same chunking/embedding process, stores in `ocr_documents` collection

At scoring time, **both collections are queried** and context is merged before the LLM call.

## Environment Variables

```bash
GROQ_API_KEY=           # Required — get from console.groq.com
REDIS_URL=              # Default: redis://localhost:6379/0
CELERY_BROKER_URL=      # Default: redis://localhost:6379/0
CELERY_RESULT_BACKEND=  # Default: redis://localhost:6379/1
VECTOR_STORE_PATH=      # Default: ./data/vector_store
UPLOAD_PATH=            # Default: ./data/uploads
GROQ_MODEL=             # Default: llama3-8b-8192
EMBEDDING_MODEL=        # Default: sentence-transformers/all-MiniLM-L6-v2
```

## Makefile Targets

```bash
make start   # Start local services
make stop    # Stop local services
make test    # Run test suite
make lint    # Run ruff + mypy
make clean   # Remove local generated data
make logs    # Follow logs
```

## Running Tests

```bash
# Locally (install deps first)
cd backend
pip install -r requirements.txt pytest
pytest tests/ -v
```
