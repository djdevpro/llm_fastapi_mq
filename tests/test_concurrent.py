"""
Tests de charge - Démontre le traitement parallèle avec RabbitMQ.

Usage:
    pytest tests/test_concurrent.py -v -s
    pytest tests/test_concurrent.py -v -s -k "test_parallel"
"""
import asyncio
import time
import pytest
import httpx

# Configuration
API_URL = "http://localhost:8007"
TIMEOUT = 60.0


class TestHealthCheck:
    """Tests de santé basiques."""
    
    def test_health(self):
        """Vérifie que l'API répond."""
        response = httpx.get(f"{API_URL}/health", timeout=10)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_health_full(self):
        """Vérifie RabbitMQ et OpenAI configurés."""
        response = httpx.get(f"{API_URL}/health/full", timeout=10)
        data = response.json()
        assert data["rabbitmq"] == "connected", "RabbitMQ non connecté"
        assert data["openai"] == "configured", "OpenAI non configuré"


class TestAsyncMode:
    """Tests du mode asynchrone (fire-and-forget)."""
    
    def test_chat_async_returns_immediately(self):
        """Vérifie que /chat/async retourne immédiatement."""
        start = time.time()
        
        response = httpx.post(
            f"{API_URL}/chat/async",
            json={"message": "Dis juste OK"},
            timeout=10
        )
        
        elapsed = time.time() - start
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data
        assert "stream_url" in data
        
        # Doit retourner en moins de 1 seconde (fire-and-forget)
        assert elapsed < 1.0, f"Trop lent: {elapsed:.2f}s (devrait être < 1s)"
        print(f"\n✓ Réponse en {elapsed*1000:.0f}ms")
    
    @pytest.mark.asyncio
    async def test_stream_receives_chunks(self):
        """Vérifie que le stream SSE reçoit les chunks."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # 1. Démarre l'écoute du stream AVANT d'envoyer la requête
            import uuid
            session_id = str(uuid.uuid4())
            
            async def listen_stream():
                chunks = []
                try:
                    async with client.stream("GET", f"{API_URL}/stream/{session_id}") as stream:
                        async for line in stream.aiter_lines():
                            if line.startswith("data:"):
                                chunks.append(line)
                                if '"type": "done"' in line or '"type":"done"' in line:
                                    break
                except Exception:
                    pass
                return chunks
            
            async def send_request():
                await asyncio.sleep(0.5)  # Laisse le temps au listener de démarrer
                return await client.post(
                    f"{API_URL}/chat/async",
                    json={"message": "Compte de 1 à 5", "session_id": session_id}
                )
            
            # Lance les deux en parallèle
            results = await asyncio.gather(listen_stream(), send_request())
            chunks = results[0]
            
            # Au moins le message "done" doit être reçu
            assert len(chunks) >= 1, "Devrait recevoir au moins le message done"
            print(f"\n✓ Reçu {len(chunks)} chunks")


class TestParallelProcessing:
    """Tests de traitement parallèle - DÉMO PRINCIPALE."""
    
    @pytest.mark.asyncio
    async def test_parallel_5_requests(self):
        """
        DÉMO: 5 requêtes envoyées simultanément.
        
        Si le système est bien parallélisé :
        - Temps total ≈ temps d'une seule requête
        - Pas 5x le temps d'une requête
        """
        NUM_REQUESTS = 5
        messages = [f"Dis juste le chiffre {i}" for i in range(1, NUM_REQUESTS + 1)]
        
        print(f"\n{'='*50}")
        print(f"  TEST: {NUM_REQUESTS} requêtes en parallèle")
        print(f"{'='*50}")
        
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            start_total = time.time()
            
            # Envoie toutes les requêtes en parallèle
            async def send_and_wait(msg: str, index: int):
                start = time.time()
                
                # 1. Envoie (fire-and-forget)
                resp = await client.post(
                    f"{API_URL}/chat/async",
                    json={"message": msg}
                )
                session_id = resp.json()["session_id"]
                queue_time = time.time() - start
                
                # 2. Attend la réponse complète via SSE
                result = ""
                async with client.stream("GET", f"{API_URL}/stream/{session_id}") as stream:
                    async for line in stream.aiter_lines():
                        if line.startswith("data:"):
                            if '"chunk"' in line:
                                # Extrait le chunk
                                import json
                                data = json.loads(line[5:].strip())
                                result += data.get("chunk", "")
                            if '"type": "done"' in line or '"type":"done"' in line:
                                break
                
                elapsed = time.time() - start
                print(f"  Requête #{index}: {elapsed:.2f}s | Queue: {queue_time*1000:.0f}ms | Réponse: {result[:30]}...")
                return elapsed
            
            # Lance toutes les requêtes en parallèle
            tasks = [send_and_wait(msg, i+1) for i, msg in enumerate(messages)]
            times = await asyncio.gather(*tasks)
            
            total_time = time.time() - start_total
            avg_time = sum(times) / len(times)
            sequential_estimate = sum(times)
            
            print(f"\n{'='*50}")
            print(f"  RÉSULTATS")
            print(f"{'='*50}")
            print(f"  Temps total:        {total_time:.2f}s")
            print(f"  Temps moyen/req:    {avg_time:.2f}s")
            print(f"  Si séquentiel:      {sequential_estimate:.2f}s")
            print(f"  Gain parallélisme:  {sequential_estimate/total_time:.1f}x")
            print(f"{'='*50}")
            
            # Vérifie le parallélisme
            # Si c'était séquentiel, total_time ≈ sum(times)
            # Si parallèle, total_time ≈ max(times)
            parallelism_ratio = sequential_estimate / total_time
            
            assert parallelism_ratio > 2.0, \
                f"Pas assez parallèle: ratio={parallelism_ratio:.1f}x (devrait être > 2x)"
            
            print(f"\n✓ Parallélisme confirmé: {parallelism_ratio:.1f}x plus rapide!")
    
    @pytest.mark.asyncio
    async def test_compare_sync_vs_async(self):
        """
        Compare le mode sync (/chat) vs async (/chat/async).
        Démontre que async libère le serveur immédiatement.
        """
        print(f"\n{'='*50}")
        print(f"  COMPARAISON: Sync vs Async")
        print(f"{'='*50}")
        
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Test mode ASYNC (fire-and-forget)
            start = time.time()
            resp = await client.post(
                f"{API_URL}/chat/async",
                json={"message": "Dis OK"}
            )
            async_time = time.time() - start
            
            print(f"  Mode ASYNC: {async_time*1000:.0f}ms (retour immédiat)")
            assert async_time < 0.5, "Mode async devrait retourner en < 500ms"
            
            # Test mode SYNC (attend la fin)
            start = time.time()
            resp = await client.post(
                f"{API_URL}/chat",
                json={"message": "Dis OK"}
            )
            # Consomme le stream
            content = resp.text
            sync_time = time.time() - start
            
            print(f"  Mode SYNC:  {sync_time:.2f}s (attend génération)")
            
            speedup = sync_time / async_time
            print(f"\n  → Mode async {speedup:.0f}x plus rapide pour libérer le serveur!")
            print(f"{'='*50}")


class TestLoadCapacity:
    """Tests de capacité sous charge."""
    
    @pytest.mark.asyncio
    async def test_queue_stats(self):
        """Vérifie les stats de la queue."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{API_URL}/stats")
            data = resp.json()
            
            assert "pending_tasks" in data
            assert data["status"] == "ok"
            print(f"\n✓ Queue stats: {data}")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_burst_10_requests(self):
        """
        Test de burst: 10 requêtes d'un coup.
        Vérifie que le système absorbe la charge.
        """
        NUM_REQUESTS = 10
        
        print(f"\n{'='*50}")
        print(f"  BURST TEST: {NUM_REQUESTS} requêtes simultanées")
        print(f"{'='*50}")
        
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            start = time.time()
            
            # Envoie toutes les requêtes en parallèle
            async def quick_send(i: int):
                resp = await client.post(
                    f"{API_URL}/chat/async",
                    json={"message": f"Test {i}"}
                )
                return resp.json()["session_id"]
            
            tasks = [quick_send(i) for i in range(NUM_REQUESTS)]
            session_ids = await asyncio.gather(*tasks)
            
            queue_time = time.time() - start
            
            # Vérifie les stats
            stats = (await client.get(f"{API_URL}/stats")).json()
            
            print(f"  {NUM_REQUESTS} requêtes mises en queue en {queue_time*1000:.0f}ms")
            print(f"  Tâches en attente: {stats['pending_tasks']}")
            print(f"  Sessions créées: {len(session_ids)}")
            
            assert len(session_ids) == NUM_REQUESTS
            assert queue_time < 2.0, f"Trop lent: {queue_time:.2f}s"
            
            print(f"\n✓ Burst absorbé avec succès!")


# Configuration pytest
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
