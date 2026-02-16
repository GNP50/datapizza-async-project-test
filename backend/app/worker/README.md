# Worker - Celery Background Processing

## Descrizione
Sistema di background processing per processamento documenti PDF con pipeline multi-stage: OCR, fact extraction, web verification, Q&A generation, vector indexing.

## Tecnologie
- **Celery** - Task queue distribuito
- **Redis** - Message broker e result backend
- **LLM Provider** - OpenAI o Ollama per AI tasks
- **Qdrant** - Vector database per semantic search

## Struttura
```
worker/
├── celery_app.py            # Configurazione Celery
├── tasks/
│   └── processing.py        # Task principale processamento
└── pipeline/                # Pipeline 5 stage
    ├── stage_a_ocr.py       # OCR extraction da PDF
    ├── stage_b_facts.py     # Estrazione fatti con LLM
    ├── stage_c_verification.py # Verifica web fatti
    ├── stage_d_qa.py        # Generazione Q&A
    └── stage_e_indexing.py  # Indicizzazione vettoriale
```

## Pipeline di Processamento

### Flow
```
Messaggio + PDF → Stage A → Stage B → Stage C → Stage D → Stage E → Risposta
```

### Stage A: OCR Extraction
- Input: PDF file
- Output: Testo estratto
- Cache: Hash contenuto file
- **Parallel Mode**: Processa pagine PDF in parallelo (solo con `OCR_PARALLEL=true`)

### Stage B: Fact Atomization
- Input: Testo estratto
- Output: Lista fatti atomici
- Cache: Hash testo

### Stage C: Web Verification
- Input: Fatti atomici
- Output: Fatti verificati con sources
- Cache: Hash singolo fatto

### Stage D: Q&A Generation
- Input: Fatti verificati
- Output: Coppie domanda-risposta
- Cache: Hash insieme fatti

### Stage E: Vector Indexing
- Input: Q&A pairs
- Output: Vettori in Qdrant
- Cache: Nessuna (sempre fresh)

## Esecuzione

```bash
# Start worker
celery -A app.worker.celery_app worker --loglevel=info

# Monitor con Flower
celery -A app.worker.celery_app flower
# Apri http://localhost:5555
```

## Configurazione

```bash
# .env

# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# LLM Provider
LLM_PROVIDER=ollama  # o openai

# Parallel Processing (per setup OpenAI)
OCR_PARALLEL=false              # Abilita processing parallelo pagine PDF
DOCUMENTS_PARALLEL=false        # Abilita processing parallelo documenti multipli
OCR_MAX_CONCURRENCY=3           # Max pagine OCR contemporanee
DOCUMENTS_MAX_CONCURRENCY=2     # Max documenti contemporanei
OCR_MAX_RETRIES=3               # Retry automatico per OCR
DOCUMENTS_MAX_RETRIES=3         # Retry automatico per documenti
```

### Parallel Processing

**OCR Parallelo** (`OCR_PARALLEL=true`):
- Attivato in `stage_a_ocr.py` → `LLMOCRBackend.extract_text()`
- Le pagine di un PDF vengono processate con `asyncio.gather()`
- Semaforo limita concorrenza a `OCR_MAX_CONCURRENCY`
- Retry con exponential backoff: `2^attempt` secondi
- Performance: ~3x più veloce per PDF multi-pagina con provider veloce

**Document Parallelo** (`DOCUMENTS_PARALLEL=true`):
- Attivato in `tasks/processing.py` → `process_message()`
- Upload multipli vengono processati contemporaneamente
- Ogni documento esegue pipeline completa (A→B→C→D→E) in parallelo
- Gestione errori per ogni documento con retry indipendente
- Performance: ~2.5x più veloce per upload multipli

**Quando usare**:
- ✅ Provider cloud veloce (OpenAI, Anthropic) con rate limits alti
- ✅ PDF con molte pagine (>5)
- ✅ Upload multipli frequenti
- ❌ Provider locale lento (Ollama CPU-only)
- ❌ Rate limits bassi
- ❌ Risorse limitate

## Utilizzo

```python
from app.worker.tasks import process_message_task

# Esegui task asincrono
task = process_message_task.delay(message_id="uuid")

# Check status
task.status  # PENDING, STARTED, SUCCESS, FAILURE
```

## Caching
Ogni stage usa Redis per cache basata su content hash:
- Riduce chiamate LLM duplicate
- Velocizza reprocessing stesso contenuto
- TTL configurabile per stage

## Monitoring
- **Flower UI**: http://localhost:5555
- **Logs**: Structured logging per ogni stage
- **Metrics**: Task success/failure rate, durata
