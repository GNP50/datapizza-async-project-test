# Datapizza AI Chatbot - Test Tecnico Backend Software Engineer

> AI Chatbot con RAG pipeline, fact-checking, upload documenti e architettura multi-provider.

---

## Cosa fa

Un'applicazione web che permette di:
- Chattare con un AI chatbot (supporto multi-provider: Ollama, OpenAI, Anthropic, Google)
- Allegare documenti alle domande (PDF, TXT, MD, codice sorgente)
- Visualizzare fact-checking delle risposte con sorgenti web verificate
- Ricerca semantica nelle chat (Ctrl+K)

---

## Quick Start

### Prerequisiti
- Docker Desktop installato
- 8GB RAM disponibili

### Switch provider in 30 secondi

Il sistema usa il framework **Datapizza AI** (`datapizza.core.clients.Client`) come layer di astrazione LLM. Cambiare provider richiede solo variabili d'ambiente:

```bash
# --- OpenAI ---
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4                  # default: gpt-4

# --- Anthropic ---
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# --- Google ---
LLM_PROVIDER=google
GOOGLE_API_KEY=AI...
# GOOGLE_MODEL=gemini-1.5-pro

# --- Mistral ---
LLM_PROVIDER=mistral
MISTRAL_API_KEY=...
# MISTRAL_MODEL=mistral-large-latest

# --- Ollama (default, locale o cloud) ---
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=https://api.ollama.com
OLLAMA_API_KEY=...
OLLAMA_MODEL=gpt-oss:120b-cloud

# --- Qualsiasi API OpenAI-compatible ---
LLM_PROVIDER=openai_like
OPENAI_LIKE_BASE_URL=https://my-custom-api.com/v1
OPENAI_LIKE_API_KEY=...
OPENAI_LIKE_MODEL=my-model
```

Nessuna modifica al codice. Il factory `get_llm_client()` in `backend/app/services/llm/client.py` risolve automaticamente il client Datapizza corretto.

### Setup

```bash
# 1. Clone
git clone <repository-url>
cd datapizza-project

# 2. Configura environment
cp .env.example .env
# Modifica .env: scegli provider e inserisci API key (vedi snippet sopra)

# 3. Avvia
docker-compose -f docker-compose.dev.yml up -d      # Ollama (dev, hot reload, debugger)
# oppure
docker-compose -f docker-compose.openai.yml up -d   # OpenAI (parallel processing abilitato)

# 4. Verifica
docker-compose -f docker-compose.dev.yml ps
```

### Accedi
- **Frontend**: http://localhost:3000

### Primo utilizzo
1. Registrati su http://localhost:3000
2. Crea una chat
3. Scrivi un messaggio, allega un documento (opzionale)
4. Visualizza risposta AI + fact-checking (bottone "View Sources" sotto la risposta)

---

## Architettura

```
                                ┌──────────────────┐
                                │    Frontend      │
                                │   (Next.js 15)   │
                                │    Port 3000     │
                                └────────┬─────────┘
                                         │ HTTP
                                ┌────────▼─────────┐
                                │    Backend       │
                                │   (FastAPI)      │
                                │    Port 8000     │
                                └────────┬─────────┘
                                         │
              ┌──────────────┬───────────┼───────────┬──────────────┐
              │              │           │           │              │
       ┌──────▼──────┐ ┌────▼────┐ ┌────▼────┐ ┌───▼────┐ ┌──────▼──────┐
       │ PostgreSQL  │ │  Redis  │ │  Celery │ │ Qdrant │ │  Provider   │
       │  Database   │ │  Cache  │ │  Worker │ │ Vector │ │  Layer      │
       └─────────────┘ └─────────┘ └────┬────┘ │ Store  │ │ (pluggable) │
                                        │      └────────┘ └─────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │  Processing        │
                              │  Pipeline (5 stage) │
                              │  A→B→C→D→E         │
                              └────────────────────┘
```

### Componenti

| Componente   | Tecnologia                                  | Descrizione                                       |
| ------------ | ------------------------------------------- | ------------------------------------------------- |
| Frontend     | Next.js 15, TypeScript, Tailwind, shadcn/ui | Chat UI, upload drag&drop, fact-checking panel    |
| Backend      | FastAPI, SQLAlchemy 2.0 (async), Pydantic   | REST API, auth JWT, business logic                |
| Worker       | Celery + Redis                              | Pipeline di processamento documenti in background |
| Database     | PostgreSQL 16                               | Dati persistenti, migrations con Alembic          |
| Cache        | Redis 7                                     | Cache multi-livello + message broker Celery       |
| Vector Store | Qdrant                                      | Semantic search, Q&A cache, ricerca chat          |

---

## Architettura Multi-Provider (Plugin System)

Il sistema e' progettato con **abstract base classes e factory pattern** per rendere ogni componente esterno facilmente sostituibile senza modificare la business logic.

### Storage Provider

```
StorageManager (ABC)
├── LocalStorageManager   ← filesystem locale (default)
├── S3StorageManager      ← AWS S3
└── [futuro] GCSManager, AzureBlobManager, NASManager...
```

**Come aggiungere un nuovo provider** (es. Google Cloud Storage):
1. Creare `GCSStorageManager(StorageManager)` implementando `upload/download/delete/exists/get_url`
2. Aggiungere il caso `"gcs"` nella factory `get_storage_manager()`
3. Settare `STORAGE_PROVIDER=gcs` nel `.env`

**File**: `backend/app/services/storage.py`

### LLM Provider (via Datapizza AI Framework)

Il sistema usa il framework **Datapizza AI** (`datapizza.core.clients.Client`) come astrazione LLM. Tutti i provider passano per la stessa interfaccia `Client`, garantendo interscambiabilita' completa:

```
datapizza.core.clients.Client (interface)
├── OllamaDatapizzaClient     ← Ollama nativo (default) - client custom
├── OpenAIClient               ← datapizza.clients.openai
├── AnthropicClient            ← datapizza.clients.anthropic
├── GoogleClient               ← datapizza.clients.google
├── MistralClient              ← datapizza.clients.mistral
└── OpenAILikeClient           ← datapizza.clients.openai_like (qualsiasi API compatible)
```

Il factory `get_llm_client()` in `client.py` risolve il provider da `LLM_PROVIDER` e restituisce il `Client` corretto. Il layer sopra (`LLMManager` + `LLMProvider` ABC) delega `generate()`, `generate_stream()`, `generate_with_context()`.

**Due livelli di astrazione**:
1. **`LLMProvider` (ABC)** → interfaccia propria del progetto (`base.py`, `manager.py`)
2. **`datapizza.Client`** → interfaccia del framework (`client.py`) con 7 provider gia' implementati

**File**: `backend/app/services/llm/client.py` (factory principale), `backend/app/services/llm/base.py`, `backend/app/services/llm/manager.py`

### OCR Provider

```
OCRBackend (ABC)
├── PyPDF2Backend         ← estrazione testo nativa da PDF (default)
└── LLMOCRBackend         ← OCR via modelli vision (multi-provider)
    ├── OpenAIImageClient     (GPT-4o-mini vision)
    ├── AnthropicImageClient  (Claude 3 Haiku vision)
    ├── GoogleImageClient     (Gemini 1.5 Flash vision)
    ├── OllamaDatapizzaClient (modelli vision locali)
    └── OpenAILikeImageClient (qualsiasi API OpenAI-compatible)
```

Il factory `get_ocr_service()` seleziona il backend in base a `OCR_PROVIDER` (pypdf2/llm).
Per il backend LLM, `get_ocr_client()` seleziona il client vision in base a `OCR_LLM_PROVIDER` (openai/anthropic/google/ollama/openai_like).

**Parallel OCR**: le pagine PDF possono essere processate in parallelo con semaphore e exponential backoff retry (`OCR_PARALLEL=true`).

**File**: `backend/app/services/ocr/ocr_service.py`

### Embedding Provider

```
BaseEmbedder (ABC)
├── OllamaEmbedder          ← embeddings via Ollama (default)
├── OpenAICompatEmbedder    ← OpenAI / qualsiasi API OpenAI-compatible
└── [futuro] HuggingFaceEmbedder, CohereEmbedder...
```

Il factory `get_embedder()` risolve automaticamente il provider:
- `EMBEDDING_PROVIDER=auto` (default): segue `LLM_PROVIDER`, oppure usa OpenAI se `OPENAI_EMBEDDING_MODEL` e' settato
- `EMBEDDING_PROVIDER=ollama/openai/openai_like`: selezione esplicita

**File**: `backend/app/services/rag/embedder.py`

### Vector Store

```
QdrantManager (singleton, lazy init)
└── Qdrant client con dimensioni embedding risolte dinamicamente
```

Attualmente usa Qdrant. L'estrazione in una ABC `VectorStoreProvider` con implementazioni per Pinecone, Weaviate, Milvus, ChromaDB richiederebbe solo:
1. Definire `VectorStoreProvider(ABC)` con `add_document/search/delete`
2. Implementare i provider
3. Factory `get_vector_store()` basata su `VECTOR_STORE_PROVIDER`

**File**: `backend/app/services/vector/qdrant.py`

---

## Processing Pipeline

Il worker Celery processa i documenti in **5 stage automatici** con cache ad ogni step:

```
PDF/File → Stage A → Stage B → Stage C → Stage D → Stage E → Risposta
           (OCR)    (Facts)   (Verify)   (Q&A)   (Index)
```

| Stage                | Descrizione                                 | Cache           |
| -------------------- | ------------------------------------------- | --------------- |
| A - Text Extraction  | OCR/estrazione testo da PDF e file testuali | `ocr:{hash}`    |
| B - Fact Atomization | LLM estrae fatti atomici dal testo          | `facts:{hash}`  |
| C - Web Verification | Verifica fatti con ricerca web (DuckDuckGo) | `verify:{hash}` |
| D - Q&A Generation   | Genera coppie domanda-risposta dai fatti    | `qa:{hash}`     |
| E - Vector Indexing  | Indicizza Q&A in Qdrant per semantic search | -               |

**Architettura modulare**: ogni stage è implementato come classe che estende `BaseStage[TInput, TOutput]`, con configurazione centralizzata in `StageConfig` e orchestrazione tramite `PipelineManager`. Il sistema supporta:
- Resumable execution da qualsiasi stage
- Batch processing con parallelizzazione configurabile
- Type-safe input/output con generics
- Aggiunta/rimozione dinamica di stage
- Cache by content hash per ogni stage

**Parallel processing**: con `DOCUMENTS_PARALLEL=true`, documenti multipli vengono processati concorrentemente (semaphore + retry).

**Fault tolerance**: ACK late, reject on worker lost, auto-retry con backoff esponenziale, Dead Letter Queue per fallimenti permanenti. In-memory processing cache previene duplicati dopo restart del worker.

**Fix Web Verification Cache**: rimosso filtro per `document_id` nella cache lookup, permettendo cache hit cross-document per fatti identici (riduzione drastica chiamate web search e LLM).

---

## Sistema di Cache Multi-Livello

| Livello               | Tecnologia                | Uso                                                             |
| --------------------- | ------------------------- | --------------------------------------------------------------- |
| L1 - Response Cache   | Redis                     | Cache key-value tradizionale per risposte                       |
| L2 - Processing Cache | PostgreSQL (content hash) | Cache per ogni stage della pipeline                             |
| L3 - Semantic Cache   | Qdrant (vector search)    | Cache hit su domande **semanticamente simili** (threshold 0.85) |
| L4 - Worker Cache     | In-memory (thread-safe)   | Previene duplicati e stale state dopo restart worker           |

La semantic cache e' il differenziatore: "Cos'e' l'AI?" e "Definisci intelligenza artificiale" producono cache hit senza nuove chiamate LLM.

La worker cache (L4) risolve il problema di stale state: quando un worker viene fermato durante il processamento, il nuovo worker non vede lo stato "bloccato" nel database ma riprende il lavoro grazie alla cache in-memory che viene ripulita ad ogni startup.

---

## API Endpoints

```
# Auth
POST /api/v1/auth/register          Registrazione utente
POST /api/v1/auth/login             Login (JWT access + refresh)
POST /api/v1/auth/refresh           Refresh token
GET  /api/v1/auth/me                Info utente corrente

# Chat
GET  /api/v1/chats                  Lista chat (paginata)
GET  /api/v1/chats/search?query=    Ricerca semantica
POST /api/v1/chats                  Crea chat
GET  /api/v1/chats/{id}             Dettagli chat
PATCH /api/v1/chats/{id}            Aggiorna titolo
DELETE /api/v1/chats/{id}           Elimina chat

# Messaggi
POST /api/v1/chats/{id}/messages                        Invia messaggio + file
POST /api/v1/chats/{id}/messages/json                   Invia messaggio solo testo
GET  /api/v1/chats/{id}/messages                        Lista messaggi (paginata)
GET  /api/v1/messages/{id}/status                       Polling stato processamento
POST /api/v1/chats/{id}/messages/{id}/retry             Riprova processamento
POST /api/v1/chats/{id}/messages/{id}/regenerate        Rigenera risposta (Deep Mode RAG)

# Documenti
GET  /api/v1/documents/{id}                      Info documento
GET  /api/v1/documents/{id}/facts                Fatti estratti
POST /api/v1/documents/{id}/reprocess            Riprocessa
POST /api/v1/documents/{id}/reprocess-from-stage  Riprocessa da stage
POST /api/v1/documents/{id}/generate-flashcards   Genera flashcard
GET  /api/v1/documents/{id}/flashcards            Lista flashcard

# Profilo & Settings
GET/PATCH /api/v1/profile           Profilo utente
GET/PATCH /api/v1/settings          Impostazioni utente
```

### Enhanced Response Generation System

Il sistema di generazione risposte supporta **due modalità operative**:

**Normal Mode (default)**: usa chunk filtrati dal vector store
- Query augmentation: LLM genera 3-5 varianti semantiche della query
- Broad search: ricerca nel vector store con tutte le varianti
- Document selection: LLM seleziona i 3 documenti più rilevanti
- Filtered retrieval: ri-cerca solo nei documenti selezionati (filter by `document_id`)
- Response generation: LLM genera risposta con chunk filtrati
- Metadata: `{"response_type": "rag", "cached": false}`

**Deep Mode** (endpoint `/regenerate`): usa documenti completi
- Stessa logica di augmentation e selection
- Carica file `.md` completi da storage (non solo chunk)
- Accesso all'intero contenuto del documento per analisi approfondite
- Metadata: `{"response_type": "rag_deep", "cached": false}`

Frontend già integrato con visualizzazione cache status, source documents e bottone "Bypass Cache" per deep mode.

---

## Stack Tecnologico

### Backend
- **FastAPI** - REST API async
- **SQLAlchemy 2.0** - ORM async con PostgreSQL
- **Celery** - Background task queue
- **Redis** - Cache + message broker
- **Alembic** - Database migrations
- **Pydantic** - Data validation
- **Datapizza AI Framework** - RAG pipeline, vector stores, agents

### Frontend
- **Next.js 15** - React framework (App Router)
- **TypeScript** - Type safety
- **Tailwind CSS + shadcn/ui** - Styling + components
- **TanStack Query** - Server state management
- **Axios** - HTTP client con interceptors JWT

### AI/ML
- **Ollama** / **OpenAI** / **Anthropic** / **Google** - LLM providers
- **Qdrant** - Vector database per semantic search
- **DuckDuckGo Search** - Web verification per fact-checking

---

## Testing

```bash
# Backend tests
cd backend && pytest
pytest --cov=app --cov-report=html --cov-report=term-missing

# Tests specifici
pytest tests/test_api/test_auth.py

# Docker test environment
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

**Test coverage**: auth, chat CRUD, messages, documents, database, security, health checks.

**API testing**: Postman collection inclusa (`postman_collection.json` + `postman_environment.json`).

---

## Struttura Progetto

```
.
├── backend/
│   ├── app/
│   │   ├── api/                  # REST endpoints
│   │   ├── core/                 # Config, security, logging
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic validation
│   │   ├── services/
│   │   │   ├── llm/              # LLM provider abstraction
│   │   │   ├── ocr/              # OCR provider abstraction
│   │   │   ├── rag/              # Embedder factory + vector store
│   │   │   ├── vector/           # Qdrant manager
│   │   │   ├── search/           # Web search service
│   │   │   ├── storage.py        # Storage provider abstraction
│   │   │   ├── cache.py          # Redis cache manager
│   │   │   └── database.py       # Database manager
│   │   └── worker/
│   │       ├── pipeline/         # 5-stage processing pipeline
│   │       ├── tasks/            # Celery task definitions
│   │       └── utils/            # State, errors, dead letter queue
│   ├── tests/                    # Test suite
│   ├── alembic/                  # Database migrations
│   └── Dockerfile
│
├── frontend-next/
│   ├── app/                      # Pages (App Router)
│   ├── components/               # React components (chat, factcheck, ui)
│   ├── lib/                      # API client, utilities
│   └── Dockerfile
│
├── docker-compose.dev.yml        # Development (Ollama, hot reload, debugger)
├── docker-compose.openai.yml     # OpenAI (parallel processing)
├── docker-compose.test.yml       # Testing (pytest in Docker)
├── config.yaml                   # YAML configuration
└── .env.example                  # Template variabili ambiente
```

---

## Configurazione Principali

```bash
# LLM Provider
LLM_PROVIDER=ollama               # ollama (default)
OLLAMA_BASE_URL=https://api.ollama.com
OLLAMA_MODEL=gpt-oss:120b-cloud

# OCR
OCR_PROVIDER=pypdf2               # pypdf2 | llm
OCR_LLM_PROVIDER=openai           # openai | anthropic | google | ollama | openai_like

# Storage
STORAGE_PROVIDER=local             # local | s3

# Embedding
EMBEDDING_PROVIDER=auto            # auto | ollama | openai | openai_like
EMBEDDING_MODEL=qwen3-embedding:4b

# Vector Store
QDRANT_URL=http://qdrant:6333

# Parallel Processing
OCR_PARALLEL=false                 # true per provider cloud veloci
DOCUMENTS_PARALLEL=false
OCR_MAX_CONCURRENCY=3
DOCUMENTS_MAX_CONCURRENCY=2
```

---

## Scelte Architetturali

| Scelta                   | Motivazione                                                                             |
| ------------------------ | --------------------------------------------------------------------------------------- |
| **Celery**               | Processamento PDF richiede tempo; API resta responsive, client fa polling               |
| **Cache multi-livello**  | Riduce chiamate LLM (risparmio costi), cache semantica per domande simili               |
| **Async/await**          | High concurrency utenti con non-blocking I/O                                            |
| **Abstract providers**   | Ogni componente esterno (LLM, OCR, storage, embeddings) sostituibile via configurazione |
| **Content hash caching** | Stesso file/testo = cache hit garantito, indipendente dall'utente                       |
| **State machine**        | Pipeline con stati espliciti previene processamenti duplicati                           |

---

## Troubleshooting

```bash
# Logs (dev)
docker-compose -f docker-compose.dev.yml logs -f backend
docker-compose -f docker-compose.dev.yml logs -f worker

# Reset completo
docker-compose -f docker-compose.dev.yml down -v && docker-compose -f docker-compose.dev.yml up -d

# Database reset
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head

# Worker non processa
docker-compose -f docker-compose.dev.yml restart worker
```
