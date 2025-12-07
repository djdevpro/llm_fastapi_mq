# 🚀 LLM Stream + RabbitMQ

POC de streaming LLM **haute performance** avec découplage via RabbitMQ. Gère des centaines d'utilisateurs simultanés grâce à une architecture distribuée.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)

## ✨ Fonctionnalités

- 🚀 **Streaming LLM** via OpenAI API (gpt-4o-mini)
- 📡 **RabbitMQ** pour le découplage producteur/consommateur
- 🔄 **SSE** (Server-Sent Events) pour le streaming temps réel
- 🐳 **Docker** avec auto-scaling des workers
- ⚡ **Mode async** : traite 100+ requêtes simultanées
- 🧪 **Tests pytest** inclus pour valider le parallélisme

---

## 📐 Architecture

### Mode Synchrone (`/chat`) - Compatibilité

```
┌─────────────┐     POST /chat      ┌─────────────────┐
│   Client    │ ──────────────────► │    FastAPI      │
│  (Browser)  │ ◄────stream──────── │    (traite)     │
└─────────────┘                     └─────────────────┘
```

### Mode Asynchrone (`/chat/async`) - Haute charge ⚡

```
┌─────────────┐    POST /chat/async   ┌─────────────────┐
│   Client    │ ────────────────────► │    FastAPI      │
│  (Browser)  │ ◄──{session_id}────── │  (fire & forget)│
└──────┬──────┘      (~50ms)          └────────┬────────┘
       │                                       │
       │                                       │ Publie tâche
       │ SSE                                   ▼
       │                              ┌─────────────────┐
       │                              │    RabbitMQ     │
       │                              │   (llm_tasks)   │
       │                              └────────┬────────┘
       │                                       │
       │                                       │ Consomme
       │                                       ▼
       │                              ┌─────────────────┐
       │                              │  LLM Worker(s)  │ ×N instances
       │                              │  (llm_worker.py)│
       │                              └────────┬────────┘
       │                                       │
       │ GET /stream/{session_id}              │ Publie chunks
       │                                       ▼
       └────────────────────────────► ┌─────────────────┐
                                      │ llm_session_{id}│
                                      └─────────────────┘
```

### Comparaison des modes

| Aspect | Sync (`/chat`) | Async (`/chat/async`) |
|--------|----------------|----------------------|
| Latence HTTP | Bloqué pendant génération | **~50ms** retour immédiat |
| Workers HTTP | 1 par requête active | Libéré instantanément |
| Scalabilité | Limitée par uvicorn | Workers indépendants |
| Charge max | ~50 req/s | **1000+ req/s** |
| Use case | Dev, tests | **Production** |

---

## ⚙️ Variables d'environnement

| Variable | Description | Défaut | Requis |
|----------|-------------|--------|--------|
| `OPENAI_API_KEY` | Clé API OpenAI | - | ✅ |
| `RABBIT_MQ` | URL de connexion RabbitMQ | - | ✅ |
| `UVICORN_WORKERS` | Nombre de workers HTTP (uvicorn) | `4` | ❌ |
| `LLM_WORKERS` | Nombre de workers LLM (traitement OpenAI) | `3` | ❌ |
| `PORT` | Port de l'API | `8007` | ❌ |

### Exemple `.env`

```env
# Requis
OPENAI_API_KEY=sk-your-openai-api-key
RABBIT_MQ=amqps://user:password@host/vhost

# Optionnel (scaling)
UVICORN_WORKERS=4
LLM_WORKERS=5
PORT=8007
```

---

## 🚀 Démarrage rapide

### 1. Configuration

```bash
cp .env.example .env
# Éditer .env avec vos clés
```

### 2. Build & Run

```bash
# Avec le script
./run.sh start

# Ou manuellement
docker build -t llm-fastapi-mq .
docker run -d --name llm-mq-poc \
  -p 8007:8007 \
  -e UVICORN_WORKERS=4 \
  -e LLM_WORKERS=5 \
  --env-file .env \
  llm-fastapi-mq
```

### 3. Vérification

```bash
# Health check complet
curl http://localhost:8007/health/full
# {"status":"ok","rabbitmq":"connected","openai":"configured"}

# Voir les logs de démarrage
docker logs llm-mq-poc
```

---

## 📡 API Endpoints

| Méthode | Endpoint | Description | Mode |
|---------|----------|-------------|------|
| `GET` | `/health` | Health check basique | - |
| `GET` | `/health/full` | Health check + statut RabbitMQ/OpenAI | - |
| `GET` | `/test` | Test connexion OpenAI | - |
| `GET` | `/stats` | Tâches en attente dans la queue | - |
| `POST` | `/chat` | Streaming synchrone (legacy) | Sync |
| `POST` | `/chat/async` | Fire-and-forget, retourne session_id | **Async** ⚡ |
| `GET` | `/stream/{session_id}` | SSE - consomme les chunks | Async |

### Exemple : Mode Async (recommandé)

```bash
# 1. Envoie la requête (retour immédiat ~50ms)
curl -X POST http://localhost:8007/chat/async \
  -H "Content-Type: application/json" \
  -d '{"message": "Explique-moi Docker"}'

# Réponse :
# {"status":"queued","session_id":"abc-123","stream_url":"/stream/abc-123"}

# 2. Écoute le stream SSE
curl -N http://localhost:8007/stream/abc-123
```

### Exemple : Mode Sync (compatibilité)

```bash
curl -N -X POST http://localhost:8007/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Bonjour !"}'
```

---

## 🧪 Tests

Tests pytest inclus pour valider le parallélisme :

```bash
# Installation des dépendances de test
pip install pytest pytest-asyncio httpx

# Lancer tous les tests
pytest tests/ -v -s

# Test spécifique : 5 requêtes parallèles
pytest tests/test_concurrent.py -v -s -k "test_parallel_5"

# Test de comparaison sync vs async
pytest tests/test_concurrent.py -v -s -k "test_compare"
```

### Exemple de sortie

```
==================================================
  TEST: 5 requêtes en parallèle
==================================================
  Requête #1: 3.21s | Queue: 45ms | Réponse: 1, 2, 3...
  Requête #2: 3.18s | Queue: 42ms | Réponse: A, B, C...
  Requête #3: 3.25s | Queue: 48ms | Réponse: ...
  Requête #4: 3.19s | Queue: 44ms | Réponse: ...
  Requête #5: 3.22s | Queue: 46ms | Réponse: ...

==================================================
  RÉSULTATS
==================================================
  Temps total:        3.45s
  Temps moyen/req:    3.21s
  Si séquentiel:      16.05s
  Gain parallélisme:  4.7x
==================================================

✓ Parallélisme confirmé: 4.7x plus rapide!
```

---

## 📊 Scaling

### Calcul du nombre de workers LLM

```
workers = (requêtes/minute) × (temps moyen génération en minutes)

Exemple :
- 100 requêtes/minute
- 30 secondes par génération (0.5 min)
- Workers nécessaires = 100 × 0.5 = 50 workers
```

### Configuration recommandée

| Charge | UVICORN_WORKERS | LLM_WORKERS | RAM estimée |
|--------|-----------------|-------------|-------------|
| Dev | 1 | 2 | 512 MB |
| Petit | 2 | 5 | 1 GB |
| Moyen | 4 | 10 | 2 GB |
| Production | 4 | 20-50 | 4-8 GB |

### Lancer avec plus de workers

```bash
docker run -d --name llm-mq-poc \
  -p 8007:8007 \
  -e UVICORN_WORKERS=4 \
  -e LLM_WORKERS=20 \
  --env-file .env \
  llm-fastapi-mq
```

### Kubernetes (production)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-api
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: api
        image: llm-fastapi-mq:latest
        env:
        - name: UVICORN_WORKERS
          value: "4"
        - name: LLM_WORKERS
          value: "10"
        resources:
          limits:
            memory: "2Gi"
            cpu: "1000m"
```

---

## 🖥️ Interface Web

### Lancer l'interface

```bash
# Windows
start chat.html

# macOS
open chat.html

# Linux
xdg-open chat.html

# Ou via serveur local
python -m http.server 3000
# Puis ouvrir http://localhost:3000/chat.html
```

### Fonctionnalités

- 💬 Chat en temps réel avec streaming
- 🔄 Switch entre mode RabbitMQ et Direct
- ⏱️ Timestamps sur les messages
- 🎯 Indicateur de typing pendant la génération
- 📊 Status indicators (API, Queue, Stream)
- 📱 Responsive design

---

## 📁 Structure du projet

```
llm_fastapi_mq/
├── main.py                 # Application FastAPI (routeur)
├── config.py               # Configuration (env vars)
├── requirements.txt        # Dépendances Python
├── Dockerfile              # Image Docker multi-workers
├── entrypoint.sh           # Lance API + Workers automatiquement
├── run.sh                  # Script de gestion
├── chat.html               # Interface web
├── pytest.ini              # Configuration pytest
├── .env                    # Variables d'environnement
├── .env.example            # Template env
├── services/
│   ├── __init__.py         # Module init
│   ├── connection_pool.py  # Pool de connexions RabbitMQ (singleton)
│   ├── llm_worker.py       # Worker LLM indépendant (scalable)
│   ├── rabbit_publisher.py # Publisher RabbitMQ
│   └── rabbit_consumer.py  # Consumer RabbitMQ
└── tests/
    ├── __init__.py
    └── test_concurrent.py  # Tests de parallélisme
```

---

## 🔧 Scripts

```bash
./run.sh start    # Build + Run
./run.sh stop     # Stop container
./run.sh restart  # Restart
./run.sh logs     # Voir les logs
./run.sh shell    # Shell dans le container
./run.sh test     # Test les endpoints
```

---

## 🐛 Troubleshooting

### Les requêtes sont traitées séquentiellement

**Cause** : Pas assez de workers LLM.

```bash
# Vérifier le nombre de workers
docker top llm-mq-poc | grep llm_worker

# Augmenter les workers
docker run -e LLM_WORKERS=10 ...
```

### Connection error OpenAI

**Cause** : Caractères `\r` dans le fichier `.env` (Windows).

```bash
# Nettoyer le fichier
sed -i 's/\r$//' .env
```

### RabbitMQ timeout / Connexion refusée

**Cause** : Limite du plan CloudAMQP gratuit (20 connexions max).

```bash
# Réduire le nombre de workers
docker run -e LLM_WORKERS=3 -e UVICORN_WORKERS=2 ...
```

### Voir les stats de la queue

```bash
curl http://localhost:8007/stats
# {"pending_tasks":5,"queue":"llm_tasks","status":"ok"}
```

---

## 📄 License

MIT

---

## 🤝 Contribution

1. Fork le projet
2. Créer une branche (`git checkout -b feature/amazing`)
3. Commit (`git commit -m 'Add amazing feature'`)
4. Push (`git push origin feature/amazing`)
5. Ouvrir une Pull Request
