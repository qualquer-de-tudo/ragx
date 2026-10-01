"""ContextEngine — busca → grafo → ranking → dedup → compressão → orçamento.

Entrega um ContextPack: texto pronto para colar num prompt, DENTRO de um
orçamento, com toda fonte preservada.

Ver docs/07-context-engine.md.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ragx.config import Config
from ragx.context import compress as compressor
from ragx.context import format as fmt_mod
from ragx.context.budget import allocate
from ragx.context.dedup import dedupe_literal, dedupe_near, mmr
from ragx.core.models import SearchResult
from ragx.embeddings import build_embedder, embedder_id
from ragx.embeddings.base import dequantize, l2_normalize, unpack_f32
from ragx.search.service import SearchFilters, search
from ragx.storage.db import open_db
from ragx.tokens import count_tokens

INTENTS_PATH = Path(__file__).parent / "intents.yaml"


@dataclass(frozen=True, slots=True)
class ContextFragment:
    document_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    tokens: int
    compressed: bool
    reason: str
    project: str = "current"
    symbol: str | None = None
    heading_path: str | None = None
    strategy: str = "none"
    chunk_id: str = ""


@dataclass(frozen=True, slots=True)
class ContextReference:
    """Um chunk já entregue nesta sessão: só a referência, nunca o conteúdo (RAGX-0159)."""

    chunk_id: str
    document_path: str
    start_line: int
    end_line: int
    tokens: int


@dataclass
class ContextPack:
    query: str
    fragments: tuple[ContextFragment, ...] = ()
    estimated_tokens: int = 0
    budget: int = 0
    sources: tuple[str, ...] = ()
    dropped: tuple[tuple[str, str], ...] = ()
    intent: str = "general"
    stats: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    #: preenchido por `apply_session`, DEPOIS do cache: o cache guarda o pack completo
    references: tuple[ContextReference, ...] = ()


@lru_cache(maxsize=1)
def _intents() -> dict[str, Any]:
    data = yaml.safe_load(INTENTS_PATH.read_text(encoding="utf-8"))
    for item in data["intents"]:
        item["_re"] = [re.compile(p, re.IGNORECASE) for p in item["patterns"]]
    return data


def detect_intent(query: str) -> dict[str, Any]:
    data = _intents()
    for item in data["intents"]:
        if any(rx.search(query) for rx in item["_re"]):
            return item
    return data["default"]


def build_context(
    cfg: Config,
    query: str,
    budget: int | None = None,
    include_graph: bool = True,
    depth: int | None = None,
    filters: SearchFilters | None = None,
    use_cache: bool = True,
) -> ContextPack:
    budget = budget or cfg.context.default_tokens
    intent = detect_intent(query)
    pack = ContextPack(query=query, budget=budget, intent=str(intent["id"]))
    t_start = time.perf_counter()

    version = _index_version(cfg) if use_cache else ""
    cache_key = _cache_key(cfg, query, budget, include_graph, depth, filters, version)
    if use_cache:
        hit = _cache_read(cfg, cache_key)
        if hit is not None:
            hit.cached = True
            return hit

    # [1] recuperação
    t0 = time.perf_counter()
    candidates, expansion_stats = _retrieve(cfg, query, include_graph, depth, intent, filters)
    t_retrieve = (time.perf_counter() - t0) * 1000
    if not candidates:
        pack.stats = {"retrieve_ms": round(t_retrieve, 2), "candidates": 0}
        return pack

    raw_tokens = sum(_tok(c) for c in candidates)
    dropped: list[tuple[str, str]] = []

    # [2] ranking por intenção
    candidates = _apply_intent(candidates, intent)

    # [3] dedup
    t0 = time.perf_counter()
    lit = dedupe_literal(candidates)
    dropped.extend((r.chunk_id, why) for r, why in lit.dropped)

    vectors, query_vec = _vectors_for(cfg, [r.chunk_id for r in lit.kept], query)
    near = dedupe_near(lit.kept, vectors, cfg.context.dedup_threshold)
    dropped.extend((r.chunk_id, why) for r, why in near.dropped)

    keep_n = max(cfg.search.limit * 3, 20)
    div = mmr(near.kept, vectors, query_vec, cfg.context.mmr_lambda, k=keep_n)
    dropped.extend((r.chunk_id, why) for r, why in div.dropped)
    t_dedup = (time.perf_counter() - t0) * 1000

    # [4] orçamento
    plan = allocate(
        div.kept, budget,
        reserve_ratio=cfg.context.reserve_ratio,
        min_sources=cfg.context.min_sources,
    )
    dropped.extend((r.chunk_id, why) for r, why in plan.dropped)

    # [5] compressão — só se ainda não couber
    t0 = time.perf_counter()
    selected = plan.selected
    if not selected and div.kept:
        # Nada coube: o melhor candidato sozinho já passa do orçamento. Devolver
        # vazio seria pior que devolver o trecho comprimido — o agente perderia
        # a única fonte relevante.
        selected = (div.kept[0],)
        dropped = [d for d in dropped if d[0] != div.kept[0].chunk_id]
    fragments = _to_fragments(selected, query, budget, cfg, force_compress=not plan.selected)
    t_compress = (time.perf_counter() - t0) * 1000

    pack.fragments = tuple(fragments)
    pack.sources = tuple(dict.fromkeys(f.document_path for f in fragments))
    pack.dropped = tuple(dropped)
    # Garantia dura: o TEXTO que sai (cabeçalhos e rodapé inclusos) fecha abaixo do
    # teto, sempre. Antes `estimated_tokens` somava só o conteúdo e ignorava ~33
    # tokens de cabeçalho por fragmento (RAGX-0154).
    total = _rendered_tokens(pack)
    while total > budget and pack.fragments:
        removed = pack.fragments[-1]
        pack.fragments = pack.fragments[:-1]
        dropped.append((f"{removed.document_path}:{removed.start_line}", "budget:overflow"))
        pack.dropped = tuple(dropped)
        pack.sources = tuple(dict.fromkeys(f.document_path for f in pack.fragments))
        total = _rendered_tokens(pack)
    fragments = list(pack.fragments)

    pack.estimated_tokens = total
    content_tokens = sum(f.tokens for f in fragments)
    pack.stats = {
        "content_tokens": content_tokens,
        "overhead_tokens": total - content_tokens,
        "candidates": len(candidates),
        "raw_tokens": raw_tokens,
        "kept": len(fragments),
        "compressed": sum(1 for f in fragments if f.compressed),
        "retrieve_ms": round(t_retrieve, 2),
        "dedup_ms": round(t_dedup, 2),
        "compress_ms": round(t_compress, 2),
        "total_ms": round((time.perf_counter() - t_start) * 1000, 2),
        **expansion_stats,
    }

    # Pack calculado durante uma indexação, ou com o índice mudando por baixo,
    # é parcial: não entra no cache (RAGX-0135).
    if use_cache and not _indexando(cfg) and _index_version(cfg) == version:
        _cache_write(cfg, cache_key, pack)
    return pack


def _rendered_tokens(pack: ContextPack) -> int:
    """Tokens do markdown que o agente recebe (sem o título), por ponto fixo.

    O rodapé traz o próprio `estimated_tokens`, então o número entra no texto que
    ele mede: começa pelo pior caso (`budget`, mesma quantidade de dígitos) e
    reitera até estabilizar.
    """
    parts = [
        (fmt_mod.header(i, f.document_path, f.start_line, f.end_line,
                        f.heading_path or f.symbol, f.compressed), f.content)
        for i, f in enumerate(pack.fragments, start=1)
    ]
    refs = _reference_tuples(pack)
    estimado = pack.budget
    n = estimado
    for _ in range(4):
        n = count_tokens(fmt_mod.markdown(
            parts, len(pack.sources), estimado, pack.budget, len(pack.dropped), references=refs
        ))
        if n == estimado:
            break
        estimado = n
    return n


# ── etapas ──────────────────────────────────────────────────────────────
def _retrieve(
    cfg: Config,
    query: str,
    include_graph: bool,
    depth: int | None,
    intent: dict[str, Any],
    filters: SearchFilters | None,
) -> tuple[list[SearchResult], dict[str, Any]]:
    """Pede bem mais do que cabe: o funil seguinte precisa ter o que descartar."""
    want = max(cfg.search.limit * 5, 25)
    if include_graph and cfg.graph.enabled:
        from ragx.graph.service import graph_search

        out = graph_search(
            cfg, query, limit=want, depth=depth or int(intent.get("graph_depth", 1)),
            filters=filters,
        )
        if out.results:
            stats: dict[str, Any] = {
                "graph_seeds": out.seeds,
                "graph_nodes": len(out.expansion.scores),
                "graph_expanded": len(out.expansion.scores) - out.seeds,
                "graph_truncated": out.expansion.truncated,
                "graph_only": out.graph_only,
            }
            if out.partial:
                stats["partial_vectors"] = out.partial
            return list(out.results), stats
    res = search(cfg, query, mode="hybrid", limit=want, filters=filters)
    stats = {"graph_seeds": 0, "graph_nodes": 0}
    if res.partial:
        stats["partial_vectors"] = res.partial
    return list(res.results), stats


def _apply_intent(results: list[SearchResult], intent: dict[str, Any]) -> list[SearchResult]:
    weights: dict[str, float] = intent.get("weights", {})
    if not weights:
        return results
    out = []
    for r in results:
        kind = str(r.metadata.get("doc_kind", "doc"))
        factor = weights.get(kind, 1.0)
        out.append(_rescore(r, r.score * factor))
    return sorted(out, key=lambda r: -r.score)


def _to_fragments(
    selected: tuple[SearchResult, ...], query: str, budget: int, cfg: Config,
    force_compress: bool = False,
) -> list[ContextFragment]:
    if not selected:
        return []
    frags: list[ContextFragment] = []
    # O alvo de compressão desconta o que o texto gasta em cabeçalhos e rodapé:
    # sem isso o fragmento comprimido "cabia" no conteúdo e estourava no texto.
    overhead = fmt_mod.footer_cost(budget) + sum(
        fmt_mod.header_cost(r.document_path, r.start_line, r.end_line, r.heading_path or r.symbol)
        for r in selected
    )
    usable = max(int(budget * (1.0 - cfg.context.reserve_ratio)) - overhead, 48)
    natural = sum(count_tokens(r.content) for r in selected)

    # `allocate` já escolheu um conjunto que cabe. Comprimir por padrão depois
    # disso só desperdiça orçamento — o agente receberia menos contexto do que
    # poderia. Só comprime quando o conjunto REALMENTE excede.
    needs_compression = cfg.context.compress and (natural > usable or force_compress)
    total_score = sum(max(r.score, 1e-6) for r in selected)

    for r in selected:
        is_code = str(r.metadata.get("doc_kind")) == "code"
        if needs_compression:
            # Alvo proporcional ao score: os melhores ficam mais inteiros.
            share = max(r.score, 1e-6) / total_score
            target = max(int(usable * share), 48)
            c = compressor.compress(r.content, target, query=query, is_code=is_code)
        else:
            c = compressor.Compressed(r.content, False, "none", 0)
        frags.append(
            ContextFragment(
                chunk_id=r.chunk_id,
                document_path=r.document_path,
                start_line=r.start_line,
                end_line=r.end_line,
                content=c.text,
                score=r.score,
                tokens=count_tokens(c.text),
                compressed=c.compressed,
                strategy=c.strategy,
                reason=str(r.metadata.get("via") or (r.matched_by[0] if r.matched_by else "hybrid")),
                project=r.project,
                symbol=r.symbol,
                heading_path=r.heading_path,
            )
        )
    return frags


def _vectors_for(
    cfg: Config, chunk_ids: list[str], query: str
) -> tuple[dict[str, np.ndarray], np.ndarray | None]:
    """Reaproveita os vetores JÁ gravados — dedup não re-embarca nada."""
    if not chunk_ids:
        return {}, None
    vectors: dict[str, np.ndarray] = {}
    with open_db(cfg.db_path, read_only=True) as conn:
        # Vetores de modelos distintos NÃO são comparáveis — e um banco que já
        # trocou de provider guarda os dois. Sem este filtro, o produto escalar
        # recebe dimensões diferentes e estoura.
        # O modelo CONFIGURADO, não o mais recente do banco (RAGX-0136): sem
        # vetores dele, a deduplicação por similaridade simplesmente não roda.
        try:
            model_id = embedder_id(cfg)
        except Exception:
            return {}, None
        ph = ",".join("?" * len(chunk_ids))
        for r in conn.execute(
            f"""SELECT chunk_id, vector, vector_q, q_scale, q_offset
                FROM embeddings WHERE model_id = ? AND chunk_id IN ({ph})""",
            [model_id, *chunk_ids],
        ):
            if r["vector"] is not None:
                vectors[r["chunk_id"]] = l2_normalize(unpack_f32(r["vector"]))
            else:
                vectors[r["chunk_id"]] = l2_normalize(
                    dequantize(r["vector_q"], r["q_scale"], r["q_offset"])
                )
    if not vectors:
        return {}, None

    dim = len(next(iter(vectors.values())))
    try:
        qv = l2_normalize(build_embedder(cfg).embed_query(query)[:dim])
    except Exception:
        return vectors, None
    return vectors, qv


def _rescore(r: SearchResult, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=r.chunk_id, document_path=r.document_path, kind=r.kind,
        start_line=r.start_line, end_line=r.end_line, score=score, content=r.content,
        project=r.project, symbol=r.symbol, heading_path=r.heading_path,
        matched_by=r.matched_by, metadata=r.metadata,
    )


def _tok(r: SearchResult) -> int:
    n = r.metadata.get("token_count")
    return n if isinstance(n, int) and n > 0 else count_tokens(r.content)


# ── cache ───────────────────────────────────────────────────────────────
#: Muda sempre que o formato do arquivo de cache muda; entrada de outro formato é miss.
CACHE_FORMAT = 3  # 3: a expansão do grafo mudou o que entra no contexto (RAGX-0145)
_CACHE_MAX_FILES = 200
_CACHE_MAX_BYTES = 32 * 1024 * 1024


@lru_cache(maxsize=1)
def _intents_hash() -> str:
    return hashlib.sha256(INTENTS_PATH.read_bytes()).hexdigest()[:16]


def _cache_key(
    cfg: Config,
    query: str,
    budget: int,
    include_graph: bool,
    depth: int | None,
    filters: SearchFilters | None = None,
    version: str | None = None,
) -> str:
    """Tudo que, se mudar, muda o pack.

    Antes a chave não tinha `filters`, os pesos de busca e do grafo, `reserve_ratio`,
    `min_sources` nem `work_paths`: `lang=markdown` e depois `lang=python`, mesma
    consulta, devolviam o MESMO pack com `cached=True` (RAGX-0135).
    """
    fingerprint = json.dumps(
        {
            "fmt": CACHE_FORMAT,
            "q": query, "b": budget, "g": include_graph, "d": depth,
            "f": None if filters is None else {
                k: getattr(filters, k) for k in ("lang", "kind", "path_glob", "min_score")
            },
            "context": cfg.context.model_dump(),
            "search": cfg.search.model_dump(),
            "graph": cfg.graph.model_dump(),
            "emb": [cfg.embedding.provider, cfg.embedding.model, cfg.embedding.dim,
                    cfg.embedding.versioned_dim, cfg.embedding.rescore],
            "work": cfg.index.work_paths, "test": cfg.index.test_paths,
            "intents": _intents_hash(),
            "v": version if version is not None else _index_version(cfg),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]


def _index_version(cfg: Config) -> str:
    """A versão do índice: geração dos vetores + a última indexação TERMINADA.

    Só run com `finished_at` e sem erro conta: uma run aberta já aparecia no
    `MAX(id)` e o pack parcial de uma indexação em andamento entrava no cache
    sob o id final. `vec_gen` (RAGX-0134) cobre o que muda vetores sem run.
    """
    if not cfg.db_path.exists():
        return "0:0"
    # Conexão mínima, e não `open_db`: o acerto de cache só precisa de duas leituras
    # e `open_db` roda PRAGMAs e checagens (~5 ms) que aqui não servem a nada.
    try:
        conn = sqlite3.connect(f"file:{cfg.db_path.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            run = conn.execute(
                "SELECT MAX(id) FROM index_runs WHERE finished_at IS NOT NULL AND error IS NULL"
            ).fetchone()
            gen = conn.execute("SELECT value FROM meta WHERE key = 'vec_gen'").fetchone()
            return f"{gen[0] if gen else '0'}:{run[0] if run and run[0] else 0}"
        finally:
            conn.close()
    except sqlite3.Error:
        return "0:0"


def _indexando(cfg: Config) -> bool:
    """Há uma indexação em curso neste projeto (trava com dono vivo)."""
    from ragx.indexing import lock

    try:
        dono = lock.holder(cfg.state_dir)
        pid = dono.get("pid") if dono else None
        return isinstance(pid, int) and lock.pid_alive(pid)
    except Exception:
        return False


def _cache_dir(cfg: Config) -> Path:
    return cfg.state_dir / "cache" / "context"


def _cache_read(cfg: Config, key: str) -> ContextPack | None:
    path = _cache_dir(cfg) / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != CACHE_FORMAT or data.get("key") != key:
            return None
        return ContextPack(
            query=data["query"],
            fragments=tuple(ContextFragment(**f) for f in data["fragments"]),
            estimated_tokens=data["estimated_tokens"],
            budget=data["budget"],
            sources=tuple(data["sources"]),
            dropped=tuple(tuple(d) for d in data["dropped"]),  # type: ignore[misc]
            intent=data.get("intent", "general"),
            stats=data.get("stats", {}),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None  # truncado, de outro formato ou de outra versão: é miss, nunca erro


def _cache_write(cfg: Config, key: str, pack: ContextPack) -> None:
    path = _cache_dir(cfg) / f"{key}.json"
    tmp = path.with_name(f".{key}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(
            json.dumps(
                {
                    "format": CACHE_FORMAT,
                    "key": key,
                    "query": pack.query,
                    "fragments": [f.__dict__ if hasattr(f, "__dict__") else _asdict(f)
                                  for f in pack.fragments],
                    "estimated_tokens": pack.estimated_tokens,
                    "budget": pack.budget,
                    "sources": list(pack.sources),
                    "dropped": [list(d) for d in pack.dropped],
                    "intent": pack.intent,
                    "stats": pack.stats,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, path)  # atômico: ninguém lê um JSON pela metade
    except OSError:
        pass  # cache é otimização, nunca motivo de falha
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
    _cache_evict(cfg)


def _cache_evict(cfg: Config) -> None:
    """No máximo `_CACHE_MAX_FILES` arquivos e `_CACHE_MAX_BYTES`; os mais antigos saem."""
    try:
        entradas = []
        for p in _cache_dir(cfg).glob("*.json"):
            st = p.stat()
            entradas.append((st.st_mtime, st.st_size, p))
    except OSError:
        return
    total = sum(e[1] for e in entradas)
    restantes = len(entradas)
    if restantes <= _CACHE_MAX_FILES and total <= _CACHE_MAX_BYTES:
        return
    for _mtime, size, p in sorted(entradas):  # do mais antigo para o mais novo
        if restantes <= _CACHE_MAX_FILES and total <= _CACHE_MAX_BYTES:
            break
        try:
            p.unlink()
        except OSError:
            continue
        restantes -= 1
        total -= size


def _asdict(f: ContextFragment) -> dict[str, Any]:
    return {s: getattr(f, s) for s in ContextFragment.__slots__}


def _reference_tuples(pack: ContextPack) -> tuple[tuple[str, str, int, int], ...]:
    return tuple((r.chunk_id, r.document_path, r.start_line, r.end_line) for r in pack.references)


def apply_session(pack: ContextPack, ledger: Any) -> ContextPack:
    """Troca por referência o que a sessão já recebeu, e registra o que está saindo agora.

    Pós-processamento do pack (o cache guarda o completo; o dedupe é da sessão): o fragmento cujo
    `chunk_id` o livro-razão viu, dentro do TTL, vira `ContextReference`; os outros ficam e passam a
    constar como entregues. Só encurta: se as referências custarem tanto quanto o conteúdo que
    substituem (um chunk minúsculo), o pack segue completo. `ledger=None` devolve o pack como veio.
    O pack recebido não é alterado.
    """
    if ledger is None or not pack.fragments:
        return pack
    novos: list[ContextFragment] = []
    refs: list[ContextReference] = []
    for f in pack.fragments:
        visto = ledger.seen(f.chunk_id) if f.chunk_id else None
        if visto is not None:
            refs.append(ContextReference(f.chunk_id, f.document_path, f.start_line, f.end_line, f.tokens))
        else:
            novos.append(f)
    if refs:
        candidato = replace(
            pack, fragments=tuple(novos), references=tuple(refs),
            sources=tuple(dict.fromkeys(f.document_path for f in novos)) or pack.sources,
            stats=dict(pack.stats),
        )
        antes, depois = _rendered_tokens(pack), _rendered_tokens(candidato)
        if depois < antes:
            candidato.estimated_tokens = depois
            candidato.stats.update({
                "kept": len(novos),
                "content_tokens": sum(f.tokens for f in novos),
                "overhead_tokens": depois - sum(f.tokens for f in novos),
                "dedupe_refs": len(refs),
                "dedupe_saved_tokens": antes - depois,
            })
            pack = candidato
    for f in pack.fragments:
        ledger.mark(f.chunk_id, f.document_path, f.start_line, f.end_line, f.tokens)
    return pack
