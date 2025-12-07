# 🚀 LLM Stream API

> **API LLM scalable** avec Celery pour gérer les requêtes OpenAI en parallèle.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-green.svg)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)
[![Tests](https://img.shields.io/badge/tests-passing-success.svg)](tests/)

---

## 🎯 Problème résolu

Les appels LLM (OpenAI) prennent **10-60 secondes** et bloquent vos workers HTTP.

**Cette architecture** :
- ⚡ Retourne **immédiatement** (~100ms)
- 🔄 Traite en **parallèle** via Celery
- 📡 Streame via **SSE** (Server-Sent Events)

---

## 📐 Architecture

```
┌─────────────┐      POST /chat       ┌─────────────────┐
│   Client    │ ────────────────────► │    FastAPI      │
│  (UI:3000)  │ ◄── task_id + session │   (API:8007)    │
└──────┬──────┘                       └────────┬────────┘
       │                                       │
       │ SSE                          ┌────────▼────────┐
       │                              │     Celery      │
       │                              │    Workers      │
       │                              └────────┬────────┘
       │                                       │
       │ GET /stream/{session}        ┌────────▼────────┐
       └──────────────────────────────┤     Redis       │
                                      └─────────────────┘
```

---

## 📁 Structure

```
llm_fastapi_mq/
├── app/                      # Code source
│   ├── api/main.py           # FastAPI
│   ├── tasks/llm_tasks.py    # Tâches Celery
│   ├── celery_app.py
│   └── config.py
│
├── docker/                   # Docker
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── entrypoint-api.sh
│   ├── entrypoint-worker.sh
│   └── docker-compose.yml
│
├── ui/                       # Interface web
│   ├── chat.html
│   └── Dockerfile
│
├── tests/
│   └── test_celery.py
│
├── run.sh
└── requirements.txt
```

---

## ⚙️ Configuration `.env`

```env
# === REQUIS ===
OPENAI_API_KEY=sk-proj-xxxxx

# === BROKER ===
BROKER=redis
REDIS_URL=redis://redis:6379/0

# Pour RabbitMQ (optionnel)
# BROKER=rabbitmq
# RABBITMQ_URL=amqps://user:pass@host/vhost

# === API ===
PORT=8007
UVICORN_WORKERS=4

# === CELERY ===
CELERY_CONCURRENCY=4
CELERY_QUEUES=high,default,low
CELERY_LOGLEVEL=info

# === MONITORING ===
FLOWER_PORT=5555

# === UI ===
WEB_PORT=3000

# === RATE LIMITING ===
LLM_RPM=500
LLM_TPM=100000
```

---

## 🚀 Démarrage

```bash
# 1. Config
cp .env.example .env

# 2. Lancer
./run.sh start

# 3. Ouvrir
#    UI:  http://localhost:3000
#    API: http://localhost:8007
#    Docs: http://localhost:8007/docs
```

---

## 📡 Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/full` | Status complet |
| `POST` | `/chat` | **Chat async (Celery)** ⚡ |
| `GET` | `/chat/{task_id}` | Status tâche |
| `GET` | `/stream/{session_id}` | Stream SSE |
| `POST` | `/embeddings` | Batch embeddings |
| `GET` | `/stats` | Stats queues |

### Exemple

```bash
# 1. Envoie (retour ~100ms)
curl -X POST http://localhost:8007/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "priority": 5}'

# Réponse:
{
  "status": "queued",
  "task_id": "xxx",
  "session_id": "yyy",
  "stream_url": "/stream/yyy"
}

# 2. Stream SSE
curl -N http://localhost:8007/stream/yyy
```

---

## 🐳 Services Docker

| Service | Port | Description |
|---------|------|-------------|
| `ui` | 3000 | Interface chat |
| `api` | 8007 | FastAPI |
| `worker` | - | Celery workers |
| `redis` | - | Broker (interne) |
| `flower` | 5555 | Monitoring (optionnel) |

---

## 🛠️ Commandes

```bash
./run.sh start         # Démarre tout
./run.sh stop          # Arrête
./run.sh restart       # Redémarre
./run.sh logs          # Tous les logs
./run.sh logs api      # Logs API
./run.sh logs worker   # Logs Worker
./run.sh status        # Status
./run.sh scale 5       # 5 workers
./run.sh monitoring    # + Flower
./run.sh test          # Tests
./run.sh build         # Build
./run.sh clean         # Nettoie
```

---

## 📊 Scaling

| Charge | Workers | Concurrency |
|--------|---------|-------------|
| Dev | 1 | 2 |
| Petit | 2 | 4 |
| Moyen | 4 | 4 |
| Prod | 8+ | 4 |

### Priorités

```python
{"priority": 10}   # → queue "high"
{"priority": 0}    # → queue "default"  
{"priority": -10}  # → queue "low"
```

---

## 🧪 Tests

```bash
pytest tests/test_celery.py -v -s
```

---

## 🔧 Features Celery

- ✅ Rate limiting (token bucket Redis)
- ✅ Retry automatique (backoff exponentiel)
- ✅ 3 queues prioritaires
- ✅ Timeout 5 min
- ✅ Monitoring Flower

---

## 📄 License

MIT
