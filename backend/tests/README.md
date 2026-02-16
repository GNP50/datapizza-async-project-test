# DataPizza Backend Tests

Questa directory contiene i test per il backend di DataPizza.

## Struttura

```
tests/
├── __init__.py
├── conftest.py                 # Fixture e configurazione pytest
├── test_api/                   # Test degli endpoint API
│   ├── __init__.py
│   ├── test_health.py          # Health check
│   ├── test_auth.py            # Autenticazione (10 tests)
│   ├── test_chats.py           # Chat CRUD e ricerca (10 tests)
│   ├── test_documents.py       # Documenti e upload (10 tests)
│   └── test_messages.py        # Messaggi e streaming (11 tests)
└── test_services/              # Test dei servizi
    ├── __init__.py
    ├── test_config.py          # Configurazione
    ├── test_database.py        # Database operations (11 tests)
    └── test_security.py        # JWT e password hashing (22 tests)
```

## Test Coverage

### Totale Test: ~76 test methods

#### API Tests (43 tests)
- **Authentication**: Registration, login, token refresh, user info
- **Chats**: CRUD, search, pagination, authorization
- **Documents**: Upload, retrieval, facts, flashcards
- **Messages**: Send, list, update, delete, search, streaming

#### Service Tests (33 tests)
- **Database**: Connection, CRUD, transactions, rollback
- **Security**: Password hashing, JWT tokens, verification

### Features Principali
- ✅ **User Management**: Test users creati e puliti automaticamente
- ✅ **Authentication**: JWT token generation e validation
- ✅ **Authorization**: Test access control e permissions
- ✅ **Database**: Database di test isolato con rollback automatico
- ✅ **Coverage**: Report di coverage completi
- ✅ **Fixtures**: Dati di test riutilizzabili

## Eseguire i Test

### Con Docker (Raccomandato)

Il modo più semplice è usare Docker Compose che configura automaticamente:
- Database PostgreSQL di test (in memoria con tmpfs)
- Redis per caching
- Qdrant per vector search
- Ollama per LLM (stessa configurazione di .dev)

```bash
# Esegui tutti i test
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Pulisci dopo i test
docker-compose -f docker-compose.test.yml down -v
```

### Localmente

Se preferisci eseguire i test localmente:

```bash
cd backend

# Installa le dipendenze di test
uv pip install -e ".[dev]"

# Esegui i test
pytest

# Con coverage
pytest --cov=app --cov-report=html

# Solo test specifici
pytest tests/test_api/
pytest tests/test_api/test_health.py
pytest -k "test_health"
```

## Variabili d'Ambiente per Test

I test utilizzano le stesse configurazioni di `.dev` ma con database separato:

- `DATABASE_URL`: Database PostgreSQL di test
- `REDIS_URL`: Redis di test
- `QDRANT_URL`: Qdrant di test
- `LLM_PROVIDER`: ollama (come in .dev)
- `OLLAMA_API_KEY`: La tua API key Ollama

## Markers

Puoi organizzare i test usando markers:

```python
@pytest.mark.unit
def test_something():
    pass

@pytest.mark.integration
async def test_api_endpoint():
    pass

@pytest.mark.slow
@pytest.mark.requires_llm
async def test_llm_feature():
    pass
```

Esegui test specifici:

```bash
# Solo test unitari
pytest -m unit

# Solo test API
pytest -m api

# Escludi test lenti
pytest -m "not slow"
```

## Coverage Report

Dopo aver eseguito i test con coverage, apri il report HTML:

```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Aggiungere Nuovi Test

1. Crea un file `test_*.py` nella directory appropriata
2. Importa le fixture necessarie da `conftest.py`
3. Usa `@pytest.mark.asyncio` per test async
4. Usa i markers appropriati

Esempio:

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.api
async def test_my_endpoint(client: AsyncClient):
    response = await client.get("/api/my-endpoint")
    assert response.status_code == 200
```
