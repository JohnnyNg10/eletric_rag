# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

工业级电力专业知识库 RAG 系统 (Industrial-grade Electric Power Standards Knowledge Base RAG System). Answers professional questions sourced from Chinese national standards (GB/DL/NB) and electric power textbooks, with strict citation traceability ("零臆测、可溯源、可校验" — zero fabrication, traceable, verifiable).

The backend lives in `backend/`. The system is in **early development** — the architecture, data models, and API scaffolding exist, but most core RAG logic (recall, rerank, generation, storage clients) are empty stubs awaiting implementation.

## Documentation Navigation

**Before searching for architecture docs, read `docs/architecture/README.md`** — it is the master index listing every architecture doc with its path and purpose. Use it to locate the right doc instead of grepping blindly. The authoritative overall design is `docs/design.md`.

Doc layout: `docs/architecture/` (core 01-03), `backend/` (04-09), `frontend/` (10-12), `modules/` (13-17, 22 — layer deep-dives), `flows/` (business/data flow diagrams), `standards/` (dev/deploy/ops).

When editing an architecture doc, changes must stay consistent across `docs/design.md`, the relevant `flows/` diagram, and the layer doc — these three describe the same system at different levels.

## Commands

All commands run from `backend/`. Dependency manager is **uv** (Python 3.13+).

```bash
uv sync                                          # install deps
cp .env.example .env                             # then edit config

uvicorn app.main:app --reload --port 8000        # dev server
celery -A app.tasks.celery_app worker --loglevel=info  # celery worker

black app/                                        # format
mypy app/                                         # type check
```

### Tests — two distinct kinds

1. **Standalone scripts** at `backend/test_*.py` (e.g. `test_preprocessing.py`, `test_model_download.py`). Run directly, NOT via pytest:
   ```bash
   cd backend && python test_preprocessing.py
   ```
   These have their own `async def main()` runner and print human-readable output. This is the current primary way modules are exercised.

2. **Pytest suite** under `backend/tests/` — scaffolded (`test_api/`, `test_core/`, `test_services/`) but currently empty. When adding pytest tests use `pytest`, `pytest --cov=app --cov-report=html`, or a single test via `pytest tests/test_core/test_x.py::test_name`.

## Architecture

### Query flow (the core RAG pipeline)

The pipeline is orchestrated by `services/query_service.py` → `QueryService.execute_query()`. The layering is deliberate and was refactored to match the design docs — **respect these boundaries**:

```
Preprocessing (preprocessing/preprocessor.py)
    → term normalization + vagueness assessment ONLY
    → may short-circuit with status="need_clarification"
Routing (retrieval/router.py → Router.route())
    → decides "fast" or "slow" lane, returns RouteDecision
Fast lane (retrieval/fast_lane.py)
    → query rewriting + metadata extraction + 3-way recall + 2-stage rerank + sufficiency check + optional retry
Slow lane (retrieval/slow_lane.py)
    → tool-calling loop for multi-hop reasoning (max 3 steps)
Generation (generation/) — stub
    → LLM answer + citations + fact validation
```

**Critical boundary**: `QueryRewriter` and `MetadataExtractor` physically live in `core/preprocessing/` but logically belong to the **fast lane**. They are imported directly by `retrieval/fast_lane.py` and are intentionally NOT re-exported from `preprocessing/__init__.py`. The `Preprocessor` class must only do term normalization + vagueness assessment. Do not add query rewriting or metadata extraction back into the preprocessing stage — that ordering bug was explicitly fixed.

Correct processing order: normalize → assess vagueness → **route** → (fast lane only) rewrite + extract metadata → recall.

### Layer-to-directory map (`backend/app/core/`)

| Directory | Layer | Status |
|-----------|-------|--------|
| `preprocessing/` | term normalizer, query optimizer (vagueness), + rewriter/metadata (owned by fast lane) | implemented |
| `retrieval/` | `router`, `fast_lane`, `slow_lane`, `recall`, `rerank`, `sufficiency` | router/lanes scaffolded, recall/rerank/sufficiency empty |
| `generation/` | `generator`, `llm_client`, `citation`, `validator` | empty stubs |
| `embedding/` | `embedder`, `model_loader` | model download implemented |

`services/` orchestrates, `storage/` wraps external stores (Qdrant/ES/Redis/MinIO — mostly stubs), `db/` holds SQLAlchemy models + repositories, `schemas/` holds Pydantic request/response models, `api/v1/endpoints/` holds routes (only `auth` and `query` are wired in `router.py`; document/user/health exist but aren't mounted).

### Startup behavior (`app/main.py`)

On startup the app: (1) checks/auto-downloads ~3.3GB of AI models via `core/model_init.py`, (2) checks the MySQL connection, (3) **auto-creates all tables and seeds initial data** via `db/session.py::init_db()` (default admin user + term dictionary). Missing models degrade gracefully (warning, not fatal); a failed DB connection is fatal.

**Schema management is via `Base.metadata.create_all()`, not Alembic migrations.** Alembic is installed and `alembic/` exists but `versions/` is empty. To change the schema, edit `db/models.py` — the tables are recreated on next startup. Don't assume migrations exist.

### Models & external services

- Embedding: `bge-large-zh-v1.5` (dense) + `efficient-splade` (sparse); Rerank: `bge-reranker-large`/`-base`. Downloaded to `models/` (gitignored). Chinese networks need `HTTP_PROXY`/`HTTPS_PROXY` set for HuggingFace access.
- Generation LLM: 豆包 Pro / 通义千问 via `LLM_BASE_URL` (Volcengine Ark endpoint by default).
- Stores: MySQL (metadata/logs), Redis (cache + Celery broker), Qdrant (vectors, hybrid dense+sparse), Elasticsearch (BM25), MinIO (raw PDFs).

## Conventions

- **Commit messages in English.** The user rejects Chinese commit messages. Follow the existing `type: subject` style (feat/refactor/docs/chore) with a detailed body.
- The `电力国标PDF/` directory holds downloaded standard PDFs and is gitignored — never commit it.
- Code comments and docstrings in this codebase are in Chinese; match that when editing existing files.
- Files carry `LF will be replaced by CRLF` warnings on Windows — this is expected, not an error.
