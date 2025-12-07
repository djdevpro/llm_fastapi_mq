# 🚀 LLM Stream API

> **API LLM scalable** avec Celery pour gérer les requêtes OpenAI en parallèle.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-green.svg)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)

---

## 🎯 Problème résolu

Les appels LLM (OpenAI, etc.) prennent **10-60 secondes** et bloquent vos workers HTTP.

**Cette architecture** :
- ⚡ Retourne **immédiatement** (~100ms)
- 🔄 Traite les requêtes **en parallèle** via Celery
- 📡 Streame la réponse via **Server-Sent Events**

---

## 📐 Architecture

```
┌─────────────┐    POST /chat/async    ┌─────────────────┐
│   Client    │ ─────────────────────► │    FastAPI      │
│             │ ◄── task_id + session  │      API        │
└──────┬──────┘                        └────────┬────────┘
       │                                        │
       │ SSE                           ┌────────▼────────┐
       │                               │     Celery      │
       │                               │    Workers      │
       │                               └────────┬────────┘
       │                                        │
       │                               ┌────────▼────────┐
       │                               │     Broker      │
       │ GET /stream/{session}         │ Redis / RabbitMQ│
       └───────────────────────────────┴─────────────────┘
```

### Brokers supportés

| Broker | Config | Use case |
|--------|--------|----------|
| **Redis** | `BROKER=redis` | Simple, rapide (défaut) |
| **RabbitMQ** | `BROKER=rabbitmq` | CloudAMQP, haute dispo |

---

## 📁 Structure du projet

```
llm_fastapi_mq/
├── app/                          # Code source
│   ├── api/
│   │   └── main.py               # FastAPI application
│   ├── tasks/
│   │   └── llm_tasks.py          # Tâches Celery
│   ├── celery_app.py             # Configuration Celery
│   └── config.py                 # Variables d'environnement
│
├── docker/                       # Docker
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── entrypoint-api.sh
│   ├── entrypoint-worker.sh
│   └── docker-compose.yml
│
├── tests/
├── chat.html                     # Interface web
├── run.sh                        # Script de gestion
└── requirements.txt
```

---

## ⚙️ Configuration

### Fichier `.env`

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

# === RATE LIMITING ===
LLM_RPM=500
LLM_TPM=100000
```

---

## 🚀 Démarrage rapide

### 1. Configuration

```bash
cp .env.example .env
# Éditer .env avec votre clé OpenAI
```

### 2. Lancer

```bash
./run.sh start
```

### 3. Vérifier

```bash
curl http://localhost:8007/health/full
```

---

## 📡 API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/full` | Status complet |
| `POST` | `/chat` | Chat sync (streaming HTTP) |
| `POST` | `/chat/async` | **Chat async (Celery)** ⚡ |
| `GET` | `/chat/{task_id}` | Status tâche |
| `GET` | `/stream/{session_id}` | Stream SSE |
| `POST` | `/embeddings` | Batch embeddings |
| `GET` | `/stats` | Stats queues |

### Exemple

```bash
# 1. Envoie (retour immédiat ~100ms)
curl -X POST http://localhost:8007/chat/async \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "priority": 5}'

# Réponse:
# {"status":"queued","task_id":"xxx","session_id":"yyy","stream_url":"/stream/yyy"}

# 2. Stream SSE
curl -N http://localhost:8007/stream/yyy
# data: {"type":"chunk","content":"Hello"}
# data: {"type":"chunk","content":"!"}
# data: {"type":"complete"}
```

---

## 🐳 Commandes

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
./run.sh test          # Test endpoints
./run.sh build         # Build images
./run.sh clean         # Nettoie tout
```

---

## 📊 Scaling

### Configurations

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

## 🖥️ Interface Web

```bash
open chat.html
```

---

## 🧪 Tests

```bash
pytest tests/test_celery.py -v -s
```

---

## 🔧 Features

| Feature | Description |
|---------|-------------|
| Rate limiting | Token bucket Redis |
| Retry auto | Backoff exponentiel |
| Priorités | 3 queues |
| Timeout | 5 min max |
| Monitoring | Flower |

---

## 📄 License

MIT
