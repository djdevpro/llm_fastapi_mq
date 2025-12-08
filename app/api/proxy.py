"""
Proxy compatible OpenAI API.

Les clients utilisent le SDK OpenAI standard avec base_url pointant vers ce proxy.
Le proxy queue les requêtes via Celery pour gérer la charge.

Usage client:
    from openai import OpenAI
    client = OpenAI(base_url="http://localhost:8007/v1", api_key="any")
    response = client.chat.completions.create(...)
"""
import asyncio
import json
import time
import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import redis.asyncio as aioredis

from app.config import REDIS_URL
from app.tasks.llm_tasks import chat_completion

router = APIRouter(prefix="/v1", tags=["OpenAI Proxy"])

# Redis client (sera initialisé via lifespan de main.py)
redis_client: Optional[aioredis.Redis] = None


async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


# ============================================================
# MODELS (compatibles OpenAI)
# ============================================================

class Message(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = "gpt-4o-mini"
    messages: List[Message]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    user: Optional[str] = None
    # Extensions proxy
    priority: Optional[int] = Field(default=0, ge=-10, le=10)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    index: int = 0
    message: Optional[Dict[str, str]] = None
    delta: Optional[Dict[str, str]] = None
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Optional[Usage] = None


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Endpoint compatible OpenAI /v1/chat/completions.
    
    Supporte streaming et non-streaming.
    Queue via Celery pour gérer la charge.
    """
    session_id = str(uuid.uuid4())
    request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    
    # Extraire le dernier message user
    user_message = ""
    system_prompt = "Tu es un assistant utile."
    
    for msg in request.messages:
        if msg.role == "system":
            system_prompt = msg.content
        elif msg.role == "user":
            user_message = msg.content
    
    if not user_message:
        raise HTTPException(400, "No user message found")
    
    # Déterminer la queue
    queue = "high" if request.priority > 5 else "low" if request.priority < -5 else "default"
    
    # Queue la tâche Celery
    task = chat_completion.apply_async(
        kwargs={
            "session_id": session_id,
            "message": user_message,
            "model": request.model,
            "system_prompt": system_prompt,
            "stream": request.stream,
            "user_id": request.user,
        },
        queue=queue,
    )
    
    if request.stream:
        return StreamingResponse(
            _stream_response(session_id, request_id, request.model),
            media_type="text/event-stream",
            headers={"X-Request-ID": request_id}
        )
    else:
        # Attendre le résultat Celery directement
        return await _wait_celery_result(task.id, request_id, request.model)


async def _stream_response(session_id: str, request_id: str, model: str):
    """Génère les events SSE au format OpenAI."""
    redis = await get_redis()
    channel = f"llm:stream:{session_id}"
    pubsub = redis.pubsub()
    
    try:
        await pubsub.subscribe(channel)
        created = int(time.time())
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                
                try:
                    parsed = json.loads(data)
                    
                    if parsed.get("type") == "chunk" and parsed.get("content"):
                        # Format OpenAI streaming
                        chunk = {
                            "id": request_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": parsed["content"]},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                    
                    elif parsed.get("type") == "complete":
                        # Final chunk avec finish_reason
                        final_chunk = {
                            "id": request_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop"
                            }]
                        }
                        yield f"data: {json.dumps(final_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        break
                    
                    elif parsed.get("type") == "error":
                        error_chunk = {
                            "error": {
                                "message": parsed.get("error", "Unknown error"),
                                "type": "server_error"
                            }
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                        break
                        
                except json.JSONDecodeError:
                    pass
                    
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def _wait_celery_result(task_id: str, request_id: str, model: str):
    """Attendre le résultat Celery directement (plus fiable pour non-streaming)."""
    from celery.result import AsyncResult
    from app.celery_app import celery
    
    created = int(time.time())
    result = AsyncResult(task_id, app=celery)
    
    # Polling async du résultat
    timeout = 120
    start = time.time()
    
    while not result.ready():
        if time.time() - start > timeout:
            raise HTTPException(504, "Request timeout")
        await asyncio.sleep(0.5)
    
    if result.failed():
        raise HTTPException(500, f"Task failed: {result.result}")
    
    task_result = result.result
    content = task_result.get("response", "") if isinstance(task_result, dict) else str(task_result)
    
    return ChatCompletionResponse(
        id=request_id,
        object="chat.completion",
        created=created,
        model=model,
        choices=[Choice(
            index=0,
            message={"role": "assistant", "content": content},
            finish_reason="stop"
        )],
        usage=Usage(
            prompt_tokens=0,
            completion_tokens=len(content.split()),
            total_tokens=len(content.split())
        )
    )


# ============================================================
# AUTRES ENDPOINTS OPENAI
# ============================================================

@router.get("/models")
async def list_models():
    """Liste des modèles disponibles."""
    return {
        "object": "list",
        "data": [
            {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"},
            {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
            {"id": "gpt-4-turbo", "object": "model", "owned_by": "openai"},
            {"id": "gpt-3.5-turbo", "object": "model", "owned_by": "openai"},
        ]
    }


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    """Détails d'un modèle."""
    return {
        "id": model_id,
        "object": "model",
        "owned_by": "openai"
    }
