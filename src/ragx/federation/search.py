"""Busca cross-project.

    projeto atual        busca híbrida completa
    projetos clonados    busca no .ragx/knowledge.db de cada um
    projetos só-federação busca na fatia pública (contratos)

Todo resultado carrega `project` — obrigatório, sem exceção: conhecimento sem
origem identificada não é entregue.

Ver docs/17-multiprojeto-e-federacao.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ragx.config import Config, load_config
from ragx.core.models import ChunkKind, SearchResult
from ragx.federation.hub import hub_db, list_projects, open_hub
from ragx.search.service import SearchFilters, SearchOutcome
from ragx.search.service import search as local_search

_WORD = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


@dataclass
class ScopedOutcome:
    results: list[SearchResult] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    degraded: dict[str, str] = field(default_factory=dict)
    scope: str = "current"


def parse_scope(scope: str) -> tuple[str, str | None]:
    if scope == "all":
        return "all", None
    if scope.startswith("project:"):
        return "project", scope.split(":", 1)[1]
    return "current", None


def search_scoped(
    cfg: Config,
    query: str,
    scope: str = "current",
    mode: str = "hybrid",
    limit: int = 10,
    filters: SearchFilters | None = None,
) -> ScopedOutcome:
    kind, target = parse_scope(scope)
    out = ScopedOutcome(scope=scope)
    current = cfg.project.name or "current"

    if kind == "current":
        local = local_search(cfg, query, mode=mode, limit=limit, filters=filters)
        out.results = [_tag(r, current) for r in local.results]
        out.projects = [current]
        if local.degraded:
            out.degraded[current] = local.degraded
        return out

    if not hub_db(cfg).exists():
        raise_no_hub()

    registry = [
        p for p in list_projects(cfg)
        if p["visibility"] != "private" and (target is None or p["name"] == target)
    ]
    if target and not registry:
        # Projeto privado ou inexistente: indistinguíveis de propósito.
        out.projects = []
        return out

    collected: list[SearchResult] = []

    include_current = target is None or target == current
    if include_current and cfg.project.visibility != "private":
        local = local_search(cfg, query, mode=mode, limit=limit, filters=filters)
        collected.extend(_tag(r, current) for r in local.results)
        out.projects.append(current)
        if local.degraded:
            out.degraded[current] = local.degraded

    penalty = cfg.hub.external_penalty
    for p in registry:
        if p["name"] == current:
            continue
        if p["cloned"] and p["path"]:
            hits, why = _search_cloned(cfg, p, query, mode, limit, filters)
            if why:
                out.degraded[p["name"]] = why
        else:
            hits = _search_federation(cfg, p, query, limit)
        if hits:
            out.projects.append(p["name"])
            collected.extend(_rescore(h, h.score * penalty) for h in hits)

    collected.sort(key=lambda r: -r.score)
    out.results = collected[:limit]
    return out


def raise_no_hub() -> None:
    from ragx.core.errors import UsageError

    raise UsageError(
        "nenhum projeto registrado — use `ragx project register <caminho>` antes de "
        "consultar com --scope all"
    )


def _search_cloned(
    cfg: Config, p: dict, query: str, mode: str, limit: int, filters: SearchFilters | None
) -> tuple[list[SearchResult], str | None]:
    try:
        other = load_config(p["path"])
    except Exception:
        return [], "configuração ilegível"
    if not other.db_path.exists():
        return [], "sem índice local (rode `ragx index` lá)"

    # Modelos distintos NÃO são comparáveis: comparar produziria ranking
    # aleatório com aparência de resultado.
    use_mode = mode
    why: str | None = None
    if p["status"] == "degraded" or (
        p["embedding_model"] and p["embedding_model"] != cfg.embedding.model
    ):
        use_mode = "keyword"
        why = "modelo de embedding divergente — só keyword"

    try:
        res: SearchOutcome = local_search(other, query, mode=use_mode, limit=limit, filters=filters)
    except Exception as exc:
        return [], f"consulta falhou ({type(exc).__name__})"
    return [_tag(r, p["name"]) for r in res.results], why


def _search_federation(cfg: Config, p: dict, query: str, limit: int) -> list[SearchResult]:
    """Projeto não clonado: só os contratos, que viajam por valor."""
    terms = {w.lower() for w in _WORD.findall(query)}
    if not terms:
        return []
    conn = open_hub(cfg, read_only=True)
    try:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM federation_items WHERE project_id = ? AND direction = 'provides'",
                (p["id"],),
            )
        ]
    finally:
        conn.close()

    out: list[SearchResult] = []
    for r in rows:
        blob = f"{r['normalized']} {r['raw']} {r['handler'] or ''}"
        hit = {w.lower() for w in _WORD.findall(blob)} & terms
        if not hit:
            continue
        body = r["contract_body"] or f"{r['kind']}: {r['normalized']}"
        out.append(
            SearchResult(
                chunk_id=f"fed:{r['id']}",
                document_path=r["source_ref"],
                kind=ChunkKind.BLOCK,
                start_line=1, end_line=1,
                score=len(hit) / max(len(terms), 1) * float(r["confidence"]),
                content=body,
                project=p["name"],
                symbol=r["normalized"],
                matched_by=("federation",),
                metadata={"kind": r["kind"], "federation_only": True,
                          "doc_kind": "config", "token_count": len(body) // 4},
            )
        )
    out.sort(key=lambda r: -r.score)
    return out[:limit]


def _tag(r: SearchResult, project: str) -> SearchResult:
    return _rescore(r, r.score, project)


def _rescore(r: SearchResult, score: float, project: str | None = None) -> SearchResult:
    return SearchResult(
        chunk_id=r.chunk_id, document_path=r.document_path, kind=r.kind,
        start_line=r.start_line, end_line=r.end_line, score=score, content=r.content,
        project=project or r.project, symbol=r.symbol, heading_path=r.heading_path,
        matched_by=r.matched_by, metadata=r.metadata,
    )
