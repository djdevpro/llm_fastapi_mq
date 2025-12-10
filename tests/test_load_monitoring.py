"""
Tests de charge avec monitoring Docker (CPU/RAM).

Usage:
    # Lancer les services d'abord
    ./run.sh start
    
    # Puis le test
    pytest tests/test_load_monitoring.py -v -s
    
    # Test spécifique
    pytest tests/test_load_monitoring.py -v -s -k "test_load_50"

Prérequis:
    pip install docker psutil
"""
import asyncio
import json
import time
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import pytest
import httpx

# Docker SDK
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    print("⚠️ docker package non installé: pip install docker")

# Configuration
API_URL = "http://localhost:8007"
TIMEOUT = 300.0

# Containers à monitorer
CONTAINERS = ["llm-api", "llm-worker", "llm-redis"]


@dataclass
class ResourceSnapshot:
    """Snapshot des ressources à un instant T."""
    timestamp: float
    container: str
    cpu_percent: float
    memory_mb: float
    memory_percent: float


@dataclass
class LoadTestResult:
    """Résultats d'un test de charge."""
    num_requests: int
    total_time: float
    successful: int
    failed: int
    avg_latency: float
    min_latency: float
    max_latency: float
    throughput: float  # req/s
    snapshots: List[ResourceSnapshot] = field(default_factory=list)
    
    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"  📊 RÉSULTATS TEST DE CHARGE")
        print(f"{'='*60}")
        print(f"  Requêtes:        {self.num_requests}")
        print(f"  Succès:          {self.successful} ({100*self.successful/self.num_requests:.0f}%)")
        print(f"  Échecs:          {self.failed}")
        print(f"  Temps total:     {self.total_time:.2f}s")
        print(f"  Throughput:      {self.throughput:.1f} req/s")
        print(f"  Latence min:     {self.min_latency:.2f}s")
        print(f"  Latence max:     {self.max_latency:.2f}s")
        print(f"  Latence moyenne: {self.avg_latency:.2f}s")
        print(f"{'='*60}")
    
    def print_resource_stats(self):
        if not self.snapshots:
            print("\n  ⚠️ Pas de données de monitoring Docker")
            return
        
        print(f"\n{'='*60}")
        print(f"  🖥️  RESSOURCES DOCKER")
        print(f"{'='*60}")
        
        # Group by container
        by_container: Dict[str, List[ResourceSnapshot]] = {}
        for snap in self.snapshots:
            if snap.container not in by_container:
                by_container[snap.container] = []
            by_container[snap.container].append(snap)
        
        for container, snaps in sorted(by_container.items()):
            if not snaps:
                continue
            
            cpu_values = [s.cpu_percent for s in snaps]
            mem_values = [s.memory_mb for s in snaps]
            
            cpu_avg = sum(cpu_values) / len(cpu_values)
            cpu_max = max(cpu_values)
            mem_avg = sum(mem_values) / len(mem_values)
            mem_max = max(mem_values)
            
            print(f"\n  📦 {container}")
            print(f"     CPU:  avg={cpu_avg:.1f}%  max={cpu_max:.1f}%")
            print(f"     RAM:  avg={mem_avg:.0f}MB  max={mem_max:.0f}MB")
        
        print(f"\n{'='*60}")


class DockerMonitor:
    """Moniteur de ressources Docker en temps réel."""
    
    def __init__(self, containers: List[str], interval: float = 0.5):
        self.containers = containers
        self.interval = interval
        self.snapshots: List[ResourceSnapshot] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._client: Optional[docker.DockerClient] = None
    
    def start(self):
        """Démarre le monitoring en background."""
        if not DOCKER_AVAILABLE:
            print("  ⚠️ Docker SDK non disponible")
            return
        
        try:
            self._client = docker.from_env()
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            print(f"  📊 Monitoring démarré pour: {', '.join(self.containers)}")
        except Exception as e:
            print(f"  ⚠️ Erreur Docker: {e}")
    
    def stop(self) -> List[ResourceSnapshot]:
        """Arrête le monitoring et retourne les snapshots."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        return self.snapshots
    
    def _monitor_loop(self):
        """Boucle de monitoring."""
        while self._running:
            for container_name in self.containers:
                try:
                    container = self._client.containers.get(container_name)
                    stats = container.stats(stream=False)
                    
                    # Calcul CPU
                    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                                stats['precpu_stats']['cpu_usage']['total_usage']
                    system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                                   stats['precpu_stats']['system_cpu_usage']
                    num_cpus = stats['cpu_stats'].get('online_cpus', 1)
                    
                    if system_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * num_cpus * 100
                    else:
                        cpu_percent = 0
                    
                    # Calcul mémoire
                    mem_usage = stats['memory_stats'].get('usage', 0)
                    mem_limit = stats['memory_stats'].get('limit', 1)
                    mem_mb = mem_usage / (1024 * 1024)
                    mem_percent = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0
                    
                    self.snapshots.append(ResourceSnapshot(
                        timestamp=time.time(),
                        container=container_name,
                        cpu_percent=cpu_percent,
                        memory_mb=mem_mb,
                        memory_percent=mem_percent
                    ))
                    
                except docker.errors.NotFound:
                    pass  # Container pas trouvé
                except Exception as e:
                    pass  # Ignore les erreurs de stats
            
            time.sleep(self.interval)


async def run_load_test(
    num_requests: int,
    message: str = "Dis juste OK",
    monitor: bool = True
) -> LoadTestResult:
    """
    Lance un test de charge avec monitoring.
    
    Args:
        num_requests: Nombre de requêtes à envoyer
        message: Message à envoyer
        monitor: Activer le monitoring Docker
    
    Returns:
        LoadTestResult avec stats et snapshots
    """
    print(f"\n{'='*60}")
    print(f"  🚀 TEST DE CHARGE: {num_requests} requêtes simultanées")
    print(f"{'='*60}")
    
    # Démarrer le monitoring
    docker_monitor = None
    if monitor:
        docker_monitor = DockerMonitor(CONTAINERS, interval=0.5)
        docker_monitor.start()
    
    # Préparer les requêtes
    latencies: List[float] = []
    errors: List[str] = []
    
    # Augmenter les limites de connexions pour le parallélisme
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=100)
    async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
        start_total = time.time()
        
        async def send_request(index: int) -> Optional[float]:
            """Envoie une requête et attend la réponse complète."""
            start = time.time()
            try:
                # 1. POST /chat (fire-and-forget)
                resp = await client.post(
                    f"{API_URL}/chat",
                    json={"message": f"{message} #{index}"}
                )
                
                if resp.status_code != 200:
                    errors.append(f"#{index}: HTTP {resp.status_code}")
                    return None
                
                data = resp.json()
                session_id = data["session_id"]
                
                # 2. Attendre la réponse via SSE
                async with client.stream("GET", f"{API_URL}/stream/{session_id}") as stream:
                    async for line in stream.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                event = json.loads(line[5:].strip())
                                if event.get("type") in ("complete", "error", "timeout"):
                                    break
                            except:
                                pass
                
                elapsed = time.time() - start
                return elapsed
                
            except Exception as e:
                errors.append(f"#{index}: {str(e)[:50]}")
                return None
        
        # Lancer toutes les requêtes en parallèle
        print(f"  ⏳ Envoi de {num_requests} requêtes...")
        tasks = [send_request(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_total
    
    # Arrêter le monitoring
    snapshots = []
    if docker_monitor:
        snapshots = docker_monitor.stop()
    
    # Analyser les résultats
    for r in results:
        if isinstance(r, float):
            latencies.append(r)
        elif isinstance(r, Exception):
            errors.append(str(r)[:50])
    
    successful = len(latencies)
    failed = num_requests - successful
    
    result = LoadTestResult(
        num_requests=num_requests,
        total_time=total_time,
        successful=successful,
        failed=failed,
        avg_latency=sum(latencies) / len(latencies) if latencies else 0,
        min_latency=min(latencies) if latencies else 0,
        max_latency=max(latencies) if latencies else 0,
        throughput=successful / total_time if total_time > 0 else 0,
        snapshots=snapshots
    )
    
    # Afficher les erreurs
    if errors:
        print(f"\n  ❌ {len(errors)} erreurs:")
        for err in errors[:5]:  # Max 5 erreurs affichées
            print(f"     - {err}")
        if len(errors) > 5:
            print(f"     ... et {len(errors) - 5} autres")
    
    return result


# ============================================================
# TESTS PYTEST
# ============================================================

class TestLoadWithMonitoring:
    """Tests de charge avec monitoring Docker."""
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Vérifie que l'API est accessible."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{API_URL}/health")
            assert resp.status_code == 200
            print(f"\n✅ API accessible")
    
    @pytest.mark.asyncio
    async def test_simultaneous_requests(self):
        """
        Test de charge simultanée.
        
        Configure via variable d'env ou directement ici:
            LOAD_TEST_COUNT=20 pytest -k test_simultaneous
        
        ⚠️ Pour des appels vraiment simultanés, assure-toi que:
           - CELERY_RATE_LIMIT=0 (ou très haut) dans .env
           - Redémarre le worker après modification
        """
        import os
        num_requests = int(os.getenv("LOAD_TEST_COUNT", "20"))
        
        result = await run_load_test(num_requests=num_requests, message="1")
        result.print_summary()
        result.print_resource_stats()
        
        # Analyse de la simultanéité
        if result.total_time > 0 and result.successful > 0:
            # Si vraiment simultané: temps_total ≈ latence_max (pas num_requests * latence)
            ratio = result.avg_latency / result.max_latency
            if ratio > 0.5:
                print(f"\n  ✅ Requêtes traitées en parallèle (ratio: {ratio:.2f})")
            else:
                print(f"\n  ⚠️ Requêtes sérialisées - vérifie CELERY_RATE_LIMIT (ratio: {ratio:.2f})")
        
        assert result.successful >= num_requests * 0.8, f"Trop d'échecs: {result.failed}"


class TestMemoryProfile:
    """Tests spécifiques pour le profiling mémoire."""
    
    @pytest.mark.asyncio
    async def test_memory_profile(self):
        """
        Profil mémoire complet: baseline → charge → récupération.
        
        Utilise seulement 10 requêtes pour économiser l'API.
        """
        import os
        num_requests = int(os.getenv("MEMORY_TEST_COUNT", "10"))
        
        print(f"\n{'='*60}")
        print(f"  📊 PROFIL MÉMOIRE ({num_requests} requêtes)")
        print(f"{'='*60}")
        
        # 1. Baseline
        print("\n  Phase 1: Baseline...")
        monitor = DockerMonitor(["llm-worker"], interval=0.5)
        monitor.start()
        await asyncio.sleep(2)
        baseline_snaps = monitor.stop()
        baseline_mem = sum(s.memory_mb for s in baseline_snaps) / len(baseline_snaps) if baseline_snaps else 0
        print(f"  → {baseline_mem:.0f}MB")
        
        # 2. Sous charge
        print(f"\n  Phase 2: Charge ({num_requests} requêtes)...")
        result = await run_load_test(num_requests=num_requests, message="1", monitor=True)
        
        load_mem = 0
        worker_snaps = [s for s in result.snapshots if "worker" in s.container]
        if worker_snaps:
            load_mem = max(s.memory_mb for s in worker_snaps)
            print(f"  → Max: {load_mem:.0f}MB (+{load_mem - baseline_mem:.0f}MB)")
        
        # 3. Récupération
        print("\n  Phase 3: Récupération...")
        await asyncio.sleep(3)
        monitor = DockerMonitor(["llm-worker"], interval=0.5)
        monitor.start()
        await asyncio.sleep(2)
        after_snaps = monitor.stop()
        after_mem = sum(s.memory_mb for s in after_snaps) / len(after_snaps) if after_snaps else 0
        print(f"  → {after_mem:.0f}MB")
        
        # Résumé
        print(f"\n{'='*60}")
        print(f"  RÉSUMÉ: {baseline_mem:.0f}MB → {load_mem:.0f}MB → {after_mem:.0f}MB")
        print(f"{'='*60}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # Test rapide en standalone
    async def main():
        result = await run_load_test(num_requests=20, message="Test")
        result.print_summary()
        result.print_resource_stats()
    
    asyncio.run(main())

