"""Benchmark local de modelos de embedding e de reranker (RAGX-0169): o HARNESS, não a decisão.

Mede, no corpus do próprio projeto, só o que JÁ está em disco: um candidato ausente é relatado como `ausente` (com a linha de como
baixar, para uma pessoa), nunca baixado nem contado como zero. Nenhum byte do projeto sai da máquina (ADR-0004): o Ollama só é
consultado em loopback, e o `.ragx/knowledge.db` real NUNCA é escrito, porque cada candidato roda numa CÓPIA do índice.

Adotar um modelo é decisão de uma pessoa (RAGX-0103); isto só dá os números.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import statistics
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

from ragx.config import Config, load_config
from ragx.core.errors import UsageError
from ragx.search.evaluation import EvalCase, ModeMetrics, evaluate
from ragx.storage.vectors import reset_vector_cache

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
#: acima disto a estimativa de tempo exige `--force-slow`
MAX_ESTIMATE_S = 20 * 60
NON_COMMERCIAL = ("cc-by-nc", "nc-")


@dataclass(frozen=True)
class Candidate:
    name: str
    provider: str  # ollama | fastembed | hashing
    model: str
    dim: int
    kind: str = "embedding"  # embedding | reranker
    license: str = ""
    how_to_get: str = ""

    @property
    def non_commercial(self) -> bool:
        return any(m in self.license.lower() for m in NON_COMMERCIAL)


@dataclass
class ModeResult:
    recall_at_5: float
    ci: tuple[float, float]
    mrr: float
    ndcg_at_10: float
    n: int


@dataclass
class BenchResult:
    candidate: Candidate
    status: str  # disponivel | ausente | incompativel
    detail: str = ""
    load_s: float | None = None
    chunks_per_s: float | None = None
    query_p50_ms: float | None = None
    query_p95_ms: float | None = None
    vector_bytes: int | None = None
    #: `conjunto -> modo -> métricas` (conjuntos: `manual`, `git`)
    metrics: dict[str, dict[str, ModeResult]] = field(default_factory=dict)
    rerank_p50_ms: float | None = None
    rerank_p95_ms: float | None = None
    license_note: str = ""


def load_candidates(path: Path) -> list[Candidate]:
    if not path.is_file():
        raise UsageError(f"arquivo de candidatos não encontrado: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [
        Candidate(
            name=i["name"], provider=i["provider"], model=i["model"], dim=int(i.get("dim", 0)),
            kind=i.get("kind", "embedding"), license=i.get("license", ""), how_to_get=i.get("how_to_get", ""),
        )
        for i in raw
    ]


def assert_loopback(base_url: str) -> None:
    """Recusa qualquer `base_url` que não seja a própria máquina: nenhum trecho do projeto pode ir para fora."""
    host = urlparse(base_url).hostname or ""
    if host not in LOOPBACK:
        raise UsageError(f"o benchmark só fala com a própria máquina; recusei {base_url!r}")


def _ollama_tags(base_url: str, timeout: float = 2.0) -> list[str] | None:
    assert_loopback(base_url)
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8", "replace"))
        return [str(m.get("name", "")) for m in dados.get("models", [])]
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def _hf_dir(model: str, kind: str) -> str | None:
    """Nome da pasta do Hugging Face que o fastembed usa para o modelo (`models--org--nome`), da lista dele; `None` se ele não o conhece."""
    try:
        if kind == "reranker":
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            catalogo = TextCrossEncoder.list_supported_models()
        else:
            from fastembed import TextEmbedding

            catalogo = TextEmbedding.list_supported_models()
    except ImportError:
        return None
    for m in catalogo:
        if m["model"] == model:
            hf = (m.get("sources") or {}).get("hf") or model
            return "models--" + hf.replace("/", "--")
    return None


def probe(
    c: Candidate,
    cfg: Config,
    ollama_tags: Callable[[str], list[str] | None] = _ollama_tags,
    cache_dirs: list[Path] | None = None,
) -> tuple[str, str]:
    """`(status, detalhe)`: `disponivel`, `ausente` ou `incompativel`, SEM baixar nada."""
    if c.provider == "hashing":
        return "disponivel", "sem modelo"
    if c.provider == "ollama":
        tags = ollama_tags(cfg.embedding.base_url)
        if tags is None:
            return "ausente", "daemon do Ollama fora do ar (ou não está em loopback)"
        nomes = {t.removesuffix(":latest") for t in tags} | set(tags)
        if c.model in nomes or c.model.removesuffix(":latest") in nomes:
            return "disponivel", "no Ollama"
        return "ausente", "não está no Ollama"
    if c.provider == "fastembed":
        pasta = _hf_dir(c.model, c.kind)
        if pasta is None:
            return "incompativel", "o fastembed instalado não conhece este modelo"
        from ragx.embeddings import legacy_models_dir, models_dir

        procurar = cache_dirs if cache_dirs is not None else [models_dir(cfg), legacy_models_dir(cfg)]
        if any((d / pasta).is_dir() for d in procurar):
            return "disponivel", "no cache do fastembed"
        return "ausente", "não está no cache do fastembed"
    return "incompativel", f"provider desconhecido: {c.provider}"


def _percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(round(p * (len(ordenados) - 1)), len(ordenados) - 1)]


def _resumo(m: ModeMetrics) -> ModeResult:
    return ModeResult(m.recall_at_5, m.recall_ci, m.mrr, m.ndcg_at_10, m.cases)


def _bench_root(cfg: Config, nome: str) -> Path:
    raiz = cfg.state_dir / "bench" / nome
    if raiz.exists():
        shutil.rmtree(raiz, ignore_errors=True)
    (raiz / ".ragx").mkdir(parents=True)
    return raiz


def _copiar_indice(origem: Path, destino: Path) -> None:
    """Cópia consistente do banco pela API de backup do SQLite: o índice real só é LIDO."""
    src = sqlite3.connect(f"file:{origem.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(destino))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def estimate_seconds(cfg: Config, c: Candidate, sample: int = 64) -> float | None:
    """Tempo estimado do reembed completo, medido embutindo `sample` chunks reais do índice com o candidato. `None` se não der."""
    from ragx.embeddings import build_embedder, reset_embedder_cache

    bcfg = _candidate_cfg(cfg, cfg.root, c)
    with sqlite3.connect(f"file:{cfg.db_path.as_posix()}?mode=ro", uri=True) as conn:
        textos = [r[0] for r in conn.execute("SELECT content FROM chunks LIMIT ?", (sample,))]
        total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    if not textos:
        return None
    reset_embedder_cache()
    try:
        emb = build_embedder(bcfg)
        t0 = time.perf_counter()
        emb.embed_documents(textos)
        return total / (len(textos) / max(time.perf_counter() - t0, 1e-9))
    except Exception:
        return None
    finally:
        reset_embedder_cache()


def _candidate_cfg(cfg: Config, raiz: Path, c: Candidate) -> Config:
    """A configuração do projeto com o embedder do candidato, apontada para a raiz do benchmark."""
    bcfg = cfg.model_copy(deep=True)
    bcfg.root = raiz
    bcfg.embedding.provider = c.provider
    bcfg.embedding.model = c.model
    bcfg.embedding.dim = c.dim
    bcfg.embedding.versioned_dim = min(bcfg.embedding.versioned_dim or c.dim, c.dim)
    # sem o cache de embedding: a vazão (chunks/s) é do MODELO, e o cache do repositório devolveria vetores prontos
    bcfg.embedding.cache = False
    return bcfg


def run_embedding(cfg: Config, c: Candidate, conjuntos: dict[str, list[EvalCase]], consultas_latencia: int = 20) -> BenchResult:
    """Reembute uma CÓPIA do índice com o candidato e avalia `semantic` e `hybrid` em cada conjunto."""
    from ragx.embeddings import build_embedder, reset_embedder_cache
    from ragx.indexing.embed import embed_pending

    res = BenchResult(c, "disponivel")
    raiz = _bench_root(cfg, c.name.replace("/", "_").replace(":", "_"))
    banco = raiz / ".ragx" / "knowledge.db"
    _copiar_indice(cfg.db_path, banco)
    bcfg = _candidate_cfg(cfg, raiz, c)
    reset_embedder_cache()
    try:
        t0 = time.perf_counter()
        emb = build_embedder(bcfg)
        emb.embed_query("aquecimento")
        res.load_s = round(time.perf_counter() - t0, 3)

        conn = sqlite3.connect(str(banco))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("DELETE FROM embeddings")
            conn.execute("DELETE FROM embedding_models")
            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            t1 = time.perf_counter()
            er = embed_pending(bcfg, conn)
            dur = max(time.perf_counter() - t1, 1e-9)
            if er.error:
                res.status, res.detail = "incompativel", er.error.splitlines()[0]
                return res
            conn.commit()
            res.chunks_per_s = round(total / dur, 1)
            res.vector_bytes = int(conn.execute("SELECT COALESCE(SUM(LENGTH(vector)), 0) FROM embeddings").fetchone()[0])
        finally:
            conn.close()

        todas = [q.query for cs in conjuntos.values() for q in cs][:consultas_latencia]
        ms: list[float] = []
        for q in todas:
            t = time.perf_counter()
            emb.embed_query(q)
            ms.append((time.perf_counter() - t) * 1000)
        if ms:
            res.query_p50_ms, res.query_p95_ms = round(statistics.median(ms), 1), round(_percentil(ms, 0.95), 1)

        reset_vector_cache()
        for nome, casos in conjuntos.items():
            res.metrics[nome] = {m.mode: _resumo(m) for m in evaluate(bcfg, casos, ("semantic", "hybrid"))}
        res.license_note = "licença não comercial: fora de qualquer recomendação" if c.non_commercial else ""
        return res
    except Exception as exc:  # um candidato que falha não derruba os outros
        res.status, res.detail = "incompativel", f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
        return res
    finally:
        reset_embedder_cache()
        shutil.rmtree(raiz, ignore_errors=True)


def run_reranker(
    cfg: Config, c: Candidate, conjuntos: dict[str, list[EvalCase]], rerank_fn: Callable[[str, list[str]], list[float]] | None = None,
    top: int = 30,
) -> BenchResult:
    """Reordena o top-30 do híbrido do índice ATUAL com o reranker e mede recall@5/MRR e a latência de 30 pares em CPU.

    `rerank_fn(consulta, textos) -> notas` existe para o teste; na prática vem do `TextCrossEncoder` do fastembed.
    Só harness: o reranker de produção é a RAGX-0108.
    """
    from ragx.search.service import search

    res = BenchResult(c, "disponivel")
    if rerank_fn is None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            from ragx.embeddings import models_dir

            modelo = TextCrossEncoder(model_name=c.model, cache_dir=str(models_dir(cfg)))
        except Exception as exc:
            res.status, res.detail = "ausente", f"{type(exc).__name__}"
            return res

        def rerank_fn(q: str, ts: list[str]) -> list[float]:  # type: ignore[misc]
            return [float(x) for x in modelo.rerank(q, ts)]

    lat: list[float] = []
    for nome, casos in conjuntos.items():
        respondidas = [k for k in casos if not k.no_answer]
        hits = 0
        mrr = 0.0
        for caso in respondidas:
            out = search(cfg, caso.query, mode="hybrid", limit=top)
            resultados = list(out.results)
            if not resultados:
                continue
            t = time.perf_counter()
            notas = rerank_fn(caso.query, [r.content for r in resultados])
            lat.append((time.perf_counter() - t) * 1000)
            ordem = [r.document_path for _, r in sorted(zip(notas, resultados, strict=True), key=lambda p: -p[0])]
            if any(p in set(ordem[:5]) for p in caso.relevant_paths):
                hits += 1
            for i, p in enumerate(ordem, start=1):
                if p in caso.relevant_paths:
                    mrr += 1.0 / i
                    break
        n = max(len(respondidas), 1)
        from ragx.search.evaluation import wilson_ci

        res.metrics[nome] = {"hybrid+rerank": ModeResult(hits / n, wilson_ci(hits, n), mrr / n, 0.0, len(respondidas))}
    if lat:
        res.rerank_p50_ms, res.rerank_p95_ms = round(statistics.median(lat), 1), round(_percentil(lat, 0.95), 1)
    res.license_note = "licença não comercial: fora de qualquer recomendação" if c.non_commercial else ""
    return res


def to_jsonable(resultados: list[BenchResult]) -> list[dict[str, object]]:
    out = []
    for r in resultados:
        d = {
            "name": r.candidate.name, "kind": r.candidate.kind, "provider": r.candidate.provider, "model": r.candidate.model,
            "status": r.status, "detail": r.detail, "load_s": r.load_s, "chunks_per_s": r.chunks_per_s,
            "query_p50_ms": r.query_p50_ms, "query_p95_ms": r.query_p95_ms, "vector_bytes": r.vector_bytes,
            "rerank_p50_ms": r.rerank_p50_ms, "rerank_p95_ms": r.rerank_p95_ms, "licenca": r.license_note or None,
            "metrics": {
                conj: {modo: {"recall_at_5": m.recall_at_5, "ci": list(m.ci), "mrr": m.mrr, "ndcg_at_10": m.ndcg_at_10, "n": m.n} for modo, m in modos.items()}
                for conj, modos in r.metrics.items()
            },
        }
        out.append(d)
    return out


def load_config_for(root: Path) -> Config:
    return load_config(root)
