# Backend - FastAPI

## Descrizione
Backend REST API costruito con FastAPI per gestire autenticazione, chat, messaggi e processamento documenti testuali (PDF, TXT, MD, codice sorgente).

## Stack Tecnologico
- **FastAPI** - Framework web async
- **SQLAlchemy 2.0** - ORM con supporto async
- **PostgreSQL** - Database relazionale
- **Redis** - Cache e message broker
- **Celery** - Task queue per processamento asincrono
- **Qdrant** - Vector database per semantic search
- **Alembic** - Migrazioni database
- **Pydantic** - Validazione dati
- **Datapizza AI Framework** - Framework AI proprietario per agents, RAG e vector operations
- **Sentence Transformers** - Embedding model (`all-MiniLM-L6-v2`) per generazione embeddings vettoriali

## Struttura
```
app/
├── api/                    # Endpoints REST
│   ├── auth.py            # Autenticazione JWT
│   ├── chats.py           # CRUD chat
│   ├── messages.py        # Invio messaggi
│   └── documents.py       # Upload documenti
├── models/                 # Modelli SQLAlchemy
│   ├── user.py
│   ├── chat.py
│   ├── message.py
│   └── document.py
├── schemas/                # Schemi Pydantic (validation)
│   ├── auth.py            # Auth schemas (login, register, tokens)
│   └── chat.py            # Chat/Message/Document schemas
├── services/               # Logica business
│   ├── database.py        # Connessione DB
│   ├── cache.py           # Redis cache
│   ├── storage.py         # File storage
│   └── vector/            # Vector search (Qdrant)
│       ├── chat_index.py  # Chat semantic search
│       ├── embeddings.py  # Embedding manager
│       └── qdrant.py      # Document vector store
├── worker/                 # Celery workers
│   ├── celery_app.py      # Configurazione
│   ├── tasks/             # Task definitions
│   └── pipeline/          # Pipeline processamento
├── core/                   # Configurazione
│   ├── config.py          # Settings
│   ├── security.py        # JWT utilities
│   └── exceptions.py      # Custom exceptions
└── main.py                # Entry point FastAPI
```

## Embedding System

Il sistema utilizza **Sentence Transformers** per generare embeddings vettoriali ad alta qualità:

### Modello Utilizzato
- **Nome**: `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensioni**: 384 dimensioni
- **Fonte**: HuggingFace Model Hub
- **Performance**: Ottimizzato per semantic similarity e ricerca vettoriale

### Caratteristiche
- ✅ **Locale**: Il modello viene scaricato e eseguito localmente (no API calls)
- ✅ **Veloce**: Inferenza rapida su CPU (~5-10ms per embedding)
- ✅ **Economico**: Nessun costo per API calls
- ✅ **Privacy**: Dati processati completamente in locale

### Utilizzo
Il modello viene utilizzato per:
1. **Chat Semantic Search** - Ricerca semantica nelle conversazioni
2. **Q&A Semantic Cache** - Cache intelligente per domande simili
3. **Document RAG** - Indicizzazione e retrieval di documenti PDF

### Configurazione
Puoi cambiare il modello di embedding tramite variabile d'ambiente:
```bash
# In .env
EMBEDDING_MODEL=all-MiniLM-L6-v2  # Default
# Altri modelli supportati:
# - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (multilingua)
# - sentence-transformers/all-mpnet-base-v2 (più accurato ma più lento)
```

## Parallel Processing Configuration

Il backend supporta **processamento parallelo** per OCR e documenti multipli:

### Variabili d'Ambiente

```bash
# Abilita/Disabilita parallelizzazione
OCR_PARALLEL=false              # Default: false (sequenziale)
DOCUMENTS_PARALLEL=false        # Default: false (sequenziale)

# Limiti di concorrenza
OCR_MAX_CONCURRENCY=3           # Max pagine OCR contemporanee
DOCUMENTS_MAX_CONCURRENCY=2     # Max documenti contemporanei
OCR_MAX_RETRIES=3               # Retry per operazioni OCR
DOCUMENTS_MAX_RETRIES=3         # Retry per documenti
```

### Comportamento

**OCR Parallelo** (`OCR_PARALLEL=true`):
- Le pagine di un PDF vengono elaborate in parallelo
- Usa `asyncio.gather()` con semaforo per limitare concorrenza
- Retry con exponential backoff (2^attempt secondi)
- Implementato in: `app/services/ocr/ocr_service.py`

**Document Parallelo** (`DOCUMENTS_PARALLEL=true`):
- Upload multipli vengono processati contemporaneamente
- Pipeline completa (OCR → Fact → Web → QA → Index) in parallelo
- Gestione errori con `return_exceptions=True`
- Implementato in: `app/worker/tasks/processing.py`

### Esempio Configurazione

**Setup OpenAI** (alta velocità):
```bash
OCR_PARALLEL=true
DOCUMENTS_PARALLEL=true
OCR_MAX_CONCURRENCY=5
DOCUMENTS_MAX_CONCURRENCY=3
```

**Setup Ollama** (locale, risorse limitate):
```bash
OCR_PARALLEL=false
DOCUMENTS_PARALLEL=false
# Concurrency settings ignorati quando parallel=false
```

### Inizializzazione
Il modello viene automaticamente scaricato da HuggingFace al primo avvio:
```
2026-02-14 11:48:16 - httpx - INFO - HTTP Request: GET https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2/xet-read-token/...
```

## Installazione
```bash
# Installa dipendenze con UV
uv sync

# Oppure con pip
pip install -r requirements.txt
```

**Nota**: Al primo avvio, il sistema scaricherà automaticamente il modello `all-MiniLM-L6-v2` (~90MB) da HuggingFace.

## Esecuzione
```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Database
```bash
# Crea migrazione
alembic revision --autogenerate -m "descrizione"

# Applica migrazioni
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Endpoints Principali

Vedi [Postman Collection](../postman_collection.json) per la collection completa.

### Authentication
- `POST /api/v1/auth/register` - Registrazione utente
- `POST /api/v1/auth/login` - Login (ritorna JWT)
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Info utente corrente
- `GET /api/v1/auth/verify-email` - Verifica email

### Chats
- `GET /api/v1/chats` - Lista chat utente
- `GET /api/v1/chats/search?query=` - Ricerca semantica chat (Qdrant)
- `POST /api/v1/chats` - Crea chat
- `GET /api/v1/chats/{id}` - Dettagli chat
- `PUT /api/v1/chats/{id}` - Aggiorna chat
- `DELETE /api/v1/chats/{id}` - Elimina chat

### Messages & Documents
- `POST /api/v1/chats/{id}/messages` - Invia messaggio + file testuali (PDF, TXT, MD, codice)
- `GET /api/v1/messages/{id}/status` - Stato processamento (polling)
- `GET /api/v1/messages/{id}` - Dettagli messaggio
- `GET /api/v1/documents/{id}` - Info documento
- `DELETE /api/v1/documents/{id}` - Elimina documento

**File supportati**: PDF, TXT, MD, Java, Python, JavaScript, TypeScript, C/C++, C#, Ruby, Go, Rust, PHP, HTML, CSS, JSON, XML, CSV, YAML

### System
- `GET /health` - Health check
- `GET /docs` - Documentazione Swagger interattiva

## Testing

### Local Testing
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/test_api/test_auth.py

# Run specific test class
pytest tests/test_api/test_auth.py::TestUserRegistration

# Run specific test method
pytest tests/test_api/test_auth.py::TestUserRegistration::test_register_new_user

# Run with verbose output
pytest -v

# Run with detailed output on failures
pytest -vv --tb=short
```

### Docker Testing
```bash
# Run tests in Docker with all services
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# View test coverage report
open backend/htmlcov/index.html
```

### Test Structure
```
tests/
├── conftest.py              # Test fixtures and configuration
├── test_api/               # API endpoint tests
│   ├── test_auth.py        # Authentication tests
│   ├── test_chats.py       # Chat CRUD tests
│   ├── test_documents.py   # Document upload/retrieval tests
│   ├── test_messages.py    # Message handling tests
│   └── test_health.py      # Health check tests
└── test_services/          # Service layer tests
    ├── test_config.py      # Configuration tests
    ├── test_database.py    # Database operations tests
    └── test_security.py    # Security/JWT tests
```

### Test Features
- ✅ **User Management**: Test users are created and cleaned up automatically
- ✅ **Authentication**: JWT token generation and validation
- ✅ **Authorization**: Test access control and permissions
- ✅ **Database**: Isolated test database with automatic rollback
- ✅ **Coverage**: Comprehensive coverage reports
- ✅ **Fixtures**: Reusable test data and setup

## Docker
```bash
docker build -f Dockerfile -t backend:latest .
docker run -p 8000:8000 backend:latest
```
