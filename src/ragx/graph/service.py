"""GraphService — reconstrução e graph-search (vetor + grafo).

É aqui que o grafo paga o próprio custo: encontrar conhecimento relacionado que
a busca híbrida pura não encontra.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import numpy as np

from ragx.config import Config
from ragx.core.models import SearchResult
from ragx.graph.extractors import reference, structural
from ragx.graph.store import EntityType, GraphStats, GraphStore
from ragx.graph.traversal import Expansion, TraversalLimits, expand
from ragx.search.hybrid import rrf
from ragx.search.ranking import diversify, rerank
from ragx.search.service import SearchFilters, filter_chunk_ids, search
from ragx.storage.db import open_db


@dataclass
class RebuildReport:
    entities: int = 0
    relations: int = 0
    unresolved: int = 0
    pruned: int = 0
    duration_ms: int = 0
    stats: GraphStats = field(default_factory=GraphStats)
    #: `update_documents` (RAGX-0151): quantos documentos foram atualizados, se caiu no rebuild completo e por quê
    documents: int = 0
    fallback_full: bool = False
    reason: str | None = None


def rebuild(cfg: Config, layers: tuple[int, ...] = (1, 2)) -> RebuildReport:
    """Reconstrói as camadas determinísticas do zero. A camada semântica
    (source='semantic') é preservada — ela custa dinheiro."""
    report = RebuildReport()
    t0 = time.perf_counter()

    with open_db(cfg.db_path) as conn:
        store = GraphStore(conn)
        store.clear(("structural", "reference"))

        by_chunk: dict[str, str] = {}
        if 1 in layers:
            ents, rels, by_chunk = structural.extract(conn)
            report.entities += store.upsert_entities(ents)
            report.relations += store.upsert_relations(rels)

        if 2 in layers:
            res = reference.extract(conn, by_chunk, cfg.root)
            report.entities += store.upsert_entities(res.entities)
            # relações só podem ser gravadas depois das entidades existirem
            known_ids = {
                r["id"] for r in conn.execute("SELECT id FROM entities")
            }
            valid = [
                rel for rel in res.relations
                if rel.src_id in known_ids and rel.dst_id in known_ids
            ]
            report.relations += store.upsert_relations(valid)
            report.unresolved = res.unresolved

        report.pruned = store.prune_orphans()
        conn.commit()
        report.stats = store.stats()

    report.duration_ms = int((time.perf_counter() - t0) * 1000)
    return report


#: manifestos de dependências: mudar um muda as tecnologias do projeto inteiro, e o caminho rápido só acrescenta
_MANIFESTOS = frozenset({
    "composer.json", "package.json", "pyproject.toml", "requirements.txt", "go.mod", "Gemfile",
})
#: acima disto o rebuild completo é mais simples e quase tão barato quanto atualizar um a um
MAX_DOCUMENTOS_INCREMENTAL = 50
_FONTES = ("structural", "reference")
_TIPOS_DO_DOCUMENTO = ("contains", "imports", "calls", "mentions")


def _lotes(itens: list[str], n: int = 400) -> Iterable[list[str]]:
    for i in range(0, len(itens), n):
        yield itens[i : i + n]


def _queda(cfg: Config, motivo: str, n_docs: int) -> RebuildReport:
    report = rebuild(cfg)
    report.fallback_full = True
    report.reason = motivo
    report.documents = n_docs
    return report


def update_documents(cfg: Config, rel_paths: Iterable[str]) -> RebuildReport:
    """Atualiza o grafo só dos documentos tocados (RAGX-0151); cai no `rebuild` completo quando a mudança não é local.

    O rebuild completo é a referência de correção: o resultado daqui é o mesmo grafo (exceto `technology` e
    `uses`, que só acrescentam). Cai no completo quando o conjunto de ENTIDADES de algum documento tocado muda
    (símbolo novo, removido ou renomeado, tabela ou rota nova), porque as relações de entrada vindas de outros
    documentos dependem dos nomes que existem; quando o documento sumiu, é novo ou é manifesto de dependências;
    quando o grafo ainda não existe; ou quando são documentos demais.

    No caminho rápido as entidades NÃO são apagadas (`ON DELETE CASCADE` derrubaria as relações vindas de outros
    documentos): só se regravam as relações que nascem dos chunks dos documentos tocados. A camada semântica
    (`source = 'semantic'`) nunca é tocada.
    """
    rels = list(dict.fromkeys(rel_paths))
    if not rels:
        return RebuildReport()
    if len(rels) > MAX_DOCUMENTOS_INCREMENTAL:
        return _queda(cfg, f"{len(rels)} documentos (mais de {MAX_DOCUMENTOS_INCREMENTAL})", len(rels))
    if any(PurePosixPath(r).name in _MANIFESTOS for r in rels):
        return _queda(cfg, "manifesto de dependências", len(rels))

    t0 = time.perf_counter()
    report = RebuildReport(documents=len(rels))
    with open_db(cfg.db_path) as conn:
        motivo = _atualizar(cfg, conn, rels, report)
    if motivo is not None:  # fora do `with`: o rebuild abre a própria conexão e não pode concorrer com esta
        return _queda(cfg, motivo, len(rels))
    report.duration_ms = int((time.perf_counter() - t0) * 1000)
    return report


def _atualizar(cfg: Config, conn: Any, rels: list[str], report: RebuildReport) -> str | None:
    """O caminho rápido. Devolve o motivo da queda (nada foi gravado) ou `None` quando atualizou e deu commit."""
    ph = ",".join("?" * len(rels))
    doc_ids = {r["id"] for r in conn.execute(f"SELECT id FROM documents WHERE rel_path IN ({ph})", rels)}
    if len(doc_ids) != len(rels):
        return "documento removido ou novo no índice"
    if conn.execute("SELECT 1 FROM entities WHERE source = 'structural' LIMIT 1").fetchone() is None:
        return "grafo ainda não construído"

    ids = sorted(doc_ids)
    dph = ",".join("?" * len(ids))
    fph = ",".join("?" * len(_FONTES))
    antes = {
        r["id"]
        for r in conn.execute(
            f"SELECT id FROM entities WHERE document_id IN ({dph}) AND source IN ({fph})", [*ids, *_FONTES]
        )
    }

    ents, rels_estruturais, by_chunk = structural.extract(conn, doc_ids)
    res = reference.extract(conn, by_chunk, cfg.root, doc_ids)
    todas = [*ents, *res.entities]
    depois = {e.id for e in todas if e.type is not EntityType.TECHNOLOGY}
    if depois != antes:
        return "conjunto de entidades mudou"

    store = GraphStore(conn)
    # 1) só as relações que nascem dos chunks dos documentos tocados (a origem está num deles; para
    #    `documented_by` o documento é o DESTINO). `uses` e a camada semântica ficam como estão.
    tph = ",".join("?" * len(_TIPOS_DO_DOCUMENTO))
    conn.execute(
        f"""DELETE FROM relations WHERE source IN ({fph}) AND (
              (type IN ({tph}) AND src_id IN (SELECT id FROM entities WHERE document_id IN ({dph})))
              OR (type = 'documented_by' AND dst_id IN (SELECT id FROM entities WHERE document_id IN ({dph}))))""",
        [*_FONTES, *_TIPOS_DO_DOCUMENTO, *ids, *ids],
    )
    # 2) entidades: upsert (mantém o id e, com ele, as relações dos outros documentos)
    report.entities += store.upsert_entities(todas)
    for e in ents:
        if e.type is EntityType.FILE:  # o upsert faz COALESCE; um título que sumiu tem de sumir
            conn.execute("UPDATE entities SET summary = ? WHERE id = ?", (e.summary, e.id))
    # 3) relações: estruturais primeiro, depois as referenciais com as duas pontas existindo
    report.relations += store.upsert_relations(rels_estruturais)
    pontas = sorted({x for rel in res.relations for x in (rel.src_id, rel.dst_id)})
    existem: set[str] = set()
    for lote in _lotes(pontas):
        lph = ",".join("?" * len(lote))
        existem.update(r["id"] for r in conn.execute(f"SELECT id FROM entities WHERE id IN ({lph})", lote))
    report.relations += store.upsert_relations(
        rel for rel in res.relations if rel.src_id in existem and rel.dst_id in existem
    )
    report.unresolved = res.unresolved
    conn.commit()
    report.stats = store.stats()
    return None


@dataclass
class GraphSearchOutcome:
    results: list[SearchResult] = field(default_factory=list)
    expansion: Expansion = field(default_factory=Expansion)
    seeds: int = 0
    #: chunks do resultado que NÃO vieram da busca base: só o grafo os trouxe
    graph_only: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)
    partial: str | None = None  # vetores parciais da busca base (RAGX-0136)
    #: o vetor da consulta da busca base, repassado ao `build_context` (RAGX-0150)
    query_vec: np.ndarray | None = field(default=None, repr=False, compare=False)


def graph_search(
    cfg: Config,
    query: str,
    limit: int | None = None,
    depth: int | None = None,
    filters: SearchFilters | None = None,
) -> GraphSearchOutcome:
    """híbrida -> entidades âncora -> expansão -> chunks -> fusão RRF."""
    limit = limit or cfg.search.limit
    out = GraphSearchOutcome()

    t0 = time.perf_counter()
    base = search(cfg, query, mode="hybrid", limit=max(limit * 2, 20), filters=filters)
    out.timings_ms["search"] = (time.perf_counter() - t0) * 1000
    out.partial = base.partial
    out.query_vec = base.query_vec
    if not base.results:
        return out

    base_rank = [r.chunk_id for r in base.results]
    by_id = {r.chunk_id: r for r in base.results}

    with open_db(cfg.db_path, read_only=True) as conn:
        store = GraphStore(conn)

        t0 = time.perf_counter()
        seeds = _seeds(conn, base_rank[: max(cfg.graph.seed_top_k, 1)], by_id)
        out.seeds = len(seeds)

        limits = TraversalLimits(
            max_depth=depth or cfg.graph.max_depth,
            max_nodes=cfg.graph.max_nodes,
            max_fanout=cfg.graph.max_fanout,
            decay=cfg.graph.decay,
        )
        out.expansion = expand(store, seeds, limits)
        out.timings_ms["graph"] = (time.perf_counter() - t0) * 1000

        # entidades expandidas -> chunks representativos
        expanded = [
            eid for eid, d in out.expansion.depth.items() if d > 0
        ][: cfg.graph.max_nodes]
        chunk_map = store.chunks_for(expanded, limit=2)

        graph_rank: list[str] = []
        reasons: dict[str, str] = {}
        for eid in sorted(expanded, key=lambda e: -out.expansion.scores.get(e, 0.0)):
            for cid in chunk_map.get(eid, []):
                if cid not in graph_rank:
                    graph_rank.append(cid)
                    reasons[cid] = out.expansion.reason.get(eid, "graph")

        # O filtro vale também para o que o grafo traz: sem isto, `path_glob`/`lang`/`kind`
        # só restringiam a busca base e o grafo reintroduzia chunks de fora (RAGX-0145).
        permitidos = filter_chunk_ids(conn, graph_rank, filters)
        graph_rank = [cid for cid in graph_rank if cid in permitidos]

        t0 = time.perf_counter()
        fused = rrf(
            {"hybrid": base_rank, "graph": graph_rank},
            {"hybrid": 1.0, "graph": 0.7},
            k=cfg.search.rrf_k,
        )
        out.timings_ms["fusion"] = (time.perf_counter() - t0) * 1000

        need = [cid for cid in fused if cid not in by_id]
        if need:
            from ragx.search.service import _hydrate

            for r in _hydrate(conn, [(cid, fused[cid]) for cid in need], {}):
                by_id[r.chunk_id] = r

    results: list[SearchResult] = []
    for cid, score in sorted(fused.items(), key=lambda kv: -kv[1]):
        r = by_id.get(cid)
        if r is None:
            continue
        meta = dict(r.metadata)
        meta["via"] = reasons.get(cid, "hybrid")
        results.append(
            SearchResult(
                chunk_id=r.chunk_id, document_path=r.document_path, kind=r.kind,
                start_line=r.start_line, end_line=r.end_line, score=score,
                content=r.content, project=r.project, symbol=r.symbol,
                heading_path=r.heading_path,
                matched_by=r.matched_by or (reasons.get(cid, "graph"),),
                metadata=meta,
            )
        )

    results = diversify(rerank(query, results), cfg.search.max_per_document)
    out.results = results[:limit]
    base_ids = set(base_rank)
    out.graph_only = sum(1 for r in out.results if r.chunk_id not in base_ids)
    return out


def _seeds(conn: Any, top: list[str], by_id: dict[str, SearchResult]) -> dict[str, float]:
    """Sementes da expansão: as entidades dos primeiros chunks da busca base, e nada além.

    A nota de âncora é a do próprio chunk. Chunk sem entidade (prosa) semeia UMA entidade de
    arquivo do seu documento, com a nota do melhor chunk daquele documento (antes, toda entidade
    de todo documento dos 100 melhores entrava com nota 1,0, acima do chunk do topo). A ordem é
    determinística: nota decrescente, depois id.
    """
    if not top:
        return {}
    seeds: dict[str, float] = {}
    com_entidade: set[str] = set()
    ph = ",".join("?" * len(top))
    for row in conn.execute(f"SELECT id, chunk_id FROM entities WHERE chunk_id IN ({ph})", top):
        com_entidade.add(row["chunk_id"])
        nota = max(by_id[row["chunk_id"]].score, 0.01) if row["chunk_id"] in by_id else 0.01
        seeds[row["id"]] = max(seeds.get(row["id"], 0.0), nota)

    prosa = [cid for cid in top if cid not in com_entidade]
    if prosa:
        ph = ",".join("?" * len(prosa))
        melhor: dict[str, float] = {}
        for row in conn.execute(f"SELECT id, document_id FROM chunks WHERE id IN ({ph})", prosa):
            nota = max(by_id[row["id"]].score, 0.01) if row["id"] in by_id else 0.01
            melhor[row["document_id"]] = max(melhor.get(row["document_id"], 0.0), nota)
        for doc_id, nota in melhor.items():
            achada = conn.execute(
                "SELECT id FROM entities WHERE document_id = ? AND type = 'file' ORDER BY id LIMIT 1",
                (doc_id,),
            ).fetchone()
            if achada is not None:
                seeds[achada["id"]] = max(seeds.get(achada["id"], 0.0), nota)
    return dict(sorted(seeds.items(), key=lambda kv: (-kv[1], kv[0])))
