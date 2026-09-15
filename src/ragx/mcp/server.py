"""Servidor MCP — casca fina sobre a API interna (ADR-0006).

    PERMITIDO                      PROIBIDO
    MCP -> KnowledgeAPI -> Store   MCP -> open(path)
                                   MCP -> subprocess
                                   MCP -> requests.get(url)

Se um agente pedir "leia o .env", não existe caminho de código que atenda: a
única coisa que este módulo sabe fazer é consultar o store — e o store, por
construção, não tem segredo dentro.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from ragx.config import Config, load_config
from ragx.diagnostics import log_exception
from ragx.dictionary import builder as dictionary_builder
from ragx.mcp.operations import WriteAPI
from ragx.mcp.orchestration import OrchestrationAPI
from ragx.mcp.playbook import playbook, short_instructions
from ragx.mcp.tools import (
    BuildContextRequest,
    SearchRequest,
    cap,
    err,
    ok,
    safe_echo,
    validate_path,
)


def _guarded(fn: Any, tool: str, cfg: Config) -> Any:
    """Falha de ferramenta vira erro ESTRUTURADO, não exceção crua.

    Sem isto o agente recebe "Error executing tool X" — uma string sem código,
    sem causa e sem nada acionável. O detalhe vai para o log; o agente recebe
    o suficiente para decidir o que fazer.
    """
    try:
        return fn()
    except Exception as exc:
        log_exception(cfg.state_dir, tool, exc)
        return err(
            "internal",
            f"{tool} falhou: {type(exc).__name__}. "
            "Detalhe em .ragx/logs/errors.log",
        )


_ORDER_HINT = (
    "Ordem recomendada: get_dictionary (orientação barata) -> search_hybrid "
    "(localizar) -> build_context (montar o contexto de trabalho) -> get_chunk "
    "(aprofundar)."
)


class RateLimiter:
    """Proteção contra loop de agente."""

    def __init__(self, per_minute: int = 60):
        self.per_minute = per_minute
        self._calls: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > 60.0:
            self._calls.popleft()
        if len(self._calls) >= self.per_minute:
            return False
        self._calls.append(now)
        return True


class KnowledgeAPI:
    """Fachada que as ferramentas chamam. Toda a lógica vive abaixo dela."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.limiter = RateLimiter(cfg.mcp.rate_per_min)
        self.project = cfg.project.name or "current"

    # ── util ────────────────────────────────────────────────────────────
    def _guard(self) -> dict[str, Any] | None:
        if not self.limiter.allow():
            return err("rate_limited", f"limite de {self.limiter.per_minute} chamadas/min atingido")
        return None

    def _hit(self, r: Any) -> dict[str, Any]:
        return {
            "project": self.project,
            "chunk_id": r.chunk_id,
            "document_path": r.document_path,
            "symbol": r.symbol,
            "heading_path": r.heading_path,
            "kind": r.kind.value,
            "lines": [r.start_line, r.end_line],
            "score": round(r.score, 6),
            "content": r.content,
            "matched_by": list(r.matched_by),
        }

    # ── ferramentas ─────────────────────────────────────────────────────
    def search(self, req: SearchRequest, mode: str) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.search.service import SearchFilters
        from ragx.search.service import search as run

        path_glob = None
        if req.path_glob:
            path_glob = validate_path(req.path_glob)
            if path_glob is None:
                return err("invalid_path", "path_glob não pode ser absoluto nem conter '..'")

        out = run(
            self.cfg, req.query, mode=mode, limit=req.limit,
            filters=SearchFilters(lang=req.lang, kind=req.kind, path_glob=path_glob),
        )
        return cap(
            ok(
                {
                    "mode": out.mode,
                    "degraded": out.degraded,
                    "results": [self._hit(r) for r in out.results],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )

    def get_document(self, path: str) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        rel = validate_path(path)
        if rel is None:
            return err("invalid_path", "caminho inválido: use caminho relativo, sem '..'")

        from ragx.storage.db import open_db
        from ragx.storage.repositories import ChunkRepo, DocumentRepo

        with open_db(self.cfg.db_path, read_only=True) as conn:
            doc = DocumentRepo(conn).get(rel)
            if doc is None:
                # NÃO tenta ler do disco. Essa distinção é a fronteira inteira.
                return err("not_found", f"documento não indexado: {safe_echo(rel)}")
            chunks = ChunkRepo(conn).for_document(rel, limit=200)
        return cap(
            ok(
                {
                    "project": self.project,
                    "document": {
                        "path": doc["rel_path"], "lang": doc["lang"],
                        "kind": doc["doc_kind"], "title": doc["title"],
                        "redacted": bool(doc["redacted"]),
                    },
                    "chunks": [
                        {
                            "chunk_id": c["id"], "ordinal": c["ordinal"], "kind": c["kind"],
                            "symbol": c["symbol"], "heading_path": c["heading_path"],
                            "lines": [c["start_line"], c["end_line"]],
                            "tokens": c["token_count"],
                        }
                        for c in chunks
                    ],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )

    def get_chunk(self, chunk_id: str) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        if not chunk_id or len(chunk_id) > 64:
            return err("invalid_id", "chunk_id inválido")

        from ragx.storage.db import open_db
        from ragx.storage.repositories import ChunkRepo

        with open_db(self.cfg.db_path, read_only=True) as conn:
            row = ChunkRepo(conn).get(chunk_id)
            if row is None:
                return err("not_found", f"chunk não encontrado: {safe_echo(chunk_id)}")
        return ok(
            {
                "project": self.project,
                "chunk_id": row["id"],
                "document_path": row["rel_path"],
                "symbol": row["symbol"],
                "heading_path": row["heading_path"],
                "kind": row["kind"],
                "lines": [row["start_line"], row["end_line"]],
                "tokens": row["token_count"],
                "content": row["content"],
            }
        )

    def get_entity(self, name: str, depth: int = 1) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.graph.store import GraphStore
        from ragx.graph.traversal import neighborhood
        from ragx.storage.db import open_db

        with open_db(self.cfg.db_path, read_only=True) as conn:
            store = GraphStore(conn)
            found = store.find(name)
            if not found:
                return err("not_found", f"entidade não encontrada: {safe_echo(name)}")
            target = found[0]
            edges = neighborhood(store, target["id"], depth=min(max(depth, 1), 2))
        return cap(
            ok(
                {
                    "project": self.project,
                    "entity": {
                        "id": target["id"], "type": target["type"], "name": target["name"],
                        "qualified_name": target["qualified_name"],
                        "confidence": target["confidence"],
                    },
                    "relations": [
                        {
                            "direction": e["direction"], "type": e["type"],
                            "other": e["other_name"], "other_type": e["other_type"],
                            "confidence": e["confidence"],
                        }
                        for e in edges
                    ],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )

    def search_graph(self, req: SearchRequest, depth: int) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.graph.service import graph_search
        from ragx.search.service import SearchFilters

        out = graph_search(
            self.cfg, req.query, limit=req.limit, depth=min(max(depth, 1), 2),
            filters=SearchFilters(lang=req.lang),
        )
        return cap(
            ok(
                {
                    "seeds": out.seeds,
                    "expanded": len(out.expansion.scores),
                    "truncated": out.expansion.truncated,
                    "results": [
                        {**self._hit(r), "via": r.metadata.get("via", "graph")}
                        for r in out.results
                    ],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )

    def build_context(self, req: BuildContextRequest) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.context.engine import build_context as run
        from ragx.context.render import render

        pack = run(
            self.cfg, req.query, budget=req.tokens, include_graph=req.include_graph
        )
        payload: dict[str, Any] = {
            "project": self.project,
            "intent": pack.intent,
            "estimated_tokens": pack.estimated_tokens,
            "budget": pack.budget,
            "sources": list(pack.sources),
            "fragments": [
                {
                    "project": f.project,
                    "document_path": f.document_path,
                    "lines": [f.start_line, f.end_line],
                    "symbol": f.symbol,
                    "heading_path": f.heading_path,
                    "compressed": f.compressed,
                    "content": f.content,
                }
                for f in pack.fragments
            ],
        }
        if req.format == "markdown":
            payload["markdown"] = render(pack, "markdown")
        return cap(ok(payload), self.cfg.mcp.max_response_bytes)

    def get_dictionary(self, section: str | None = None) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        data = dictionary_builder.load(self.cfg)
        if data is None:
            try:
                data, _ = dictionary_builder.build(self.cfg)
            except Exception:
                return err("not_found", "dicionário indisponível: rode `ragx dictionary generate`")
        if section:
            if section not in data:
                return err(
                    "not_found",
                    f"seção desconhecida: {safe_echo(section, 40)} (disponíveis: {', '.join(sorted(data))})",
                )
            data = {section: data[section]}
        return cap(ok({"project": self.project, "dictionary": data}),
                   self.cfg.mcp.max_response_bytes)

    def list_projects(self) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.federation import hub, linker

        atual = {
            "name": self.project, "id": self.cfg.project.id,
            "kind": self.cfg.project.kind, "cloned": True,
            "visibility": self.cfg.project.visibility,
        }
        if not hub.hub_db(self.cfg).exists():
            return ok({"projects": [atual], "integrations": [], "unresolved": []})
        d = linker.workspace_dictionary(self.cfg)
        return cap(
            ok(
                {
                    "projects": d["projects"] or [atual],
                    "integrations": d["integrations"],
                    "unresolved": d["unresolved_consumes"],
                    "divergences": d["divergences"],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )

    def get_contract(self, kind: str, name: str) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.federation import hub, linker

        if not hub.hub_db(self.cfg).exists():
            return err("not_found", "nenhum projeto registrado no hub")
        found = linker.find_contract(self.cfg, kind, name)
        if found is None:
            return err("not_found", f"contrato não encontrado: {safe_echo(name)}")
        return ok(
            {
                "project": found["project"],
                "kind": found["kind"],
                "normalized": found["normalized"],
                "handler": found["handler"],
                "source": found["source_ref"],
                "confidence": found["confidence"],
                "contract": found["contract_body"],
            }
        )

    def search_scoped(self, req: SearchRequest, mode: str) -> dict[str, Any]:
        """`scope` != current cruza projetos — a fronteira é a mesma: o MCP
        consulta o hub e os stores, nunca o filesystem deles."""
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.federation.search import search_scoped as run
        from ragx.search.service import SearchFilters

        try:
            out = run(
                self.cfg, req.query, scope=req.scope, mode=mode, limit=req.limit,
                filters=SearchFilters(lang=req.lang, kind=req.kind),
            )
        except Exception as exc:
            return err("invalid_scope", str(exc).splitlines()[0])
        return cap(
            ok(
                {
                    "mode": mode, "scope": req.scope,
                    "projects": out.projects,
                    "degraded": out.degraded or None,
                    "results": [{**self._hit(r), "project": r.project} for r in out.results],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )


def build_server(
    cfg: Config, allow_index: bool = False, allow_write: bool | None = None
) -> Any:
    from mcp.server.mcpserver import MCPServer

    write_enabled = cfg.mcp.allow_write if allow_write is None else allow_write
    api = KnowledgeAPI(cfg)
    ops = WriteAPI(cfg, enabled=write_enabled)
    orq = OrchestrationAPI(cfg, enabled=write_enabled)
    server = MCPServer(
        name="ragx",
        instructions=short_instructions(write_enabled) + " " + _ORDER_HINT,
    )

    @server.tool(description="Como operar o RAGX: ordem das ferramentas, quando reindexar e o que o índice NÃO faz. Leia uma vez no início da sessão.")
    def get_playbook() -> dict[str, Any]:
        return _guarded(
            lambda: ok(playbook(cfg, write_enabled)), "get_playbook", cfg
        )

    @server.tool(description="Mapa barato do projeto: tecnologias, serviços, módulos, convenções. Comece por aqui.")
    def get_dictionary(section: str | None = None) -> dict[str, Any]:
        return _guarded(lambda: api.get_dictionary(section), "get_dictionary", cfg)

    @server.tool(description="Busca semântica no conhecimento indexado.")
    def search_knowledge(
        query: str, limit: int = 10, lang: str | None = None,
        kind: str | None = None, path_glob: str | None = None, scope: str = "current",
    ) -> dict[str, Any]:
        return _guarded(
            lambda: api.search(
                SearchRequest(query=query, limit=limit, lang=lang, kind=kind,
                              path_glob=path_glob, scope=scope),
                mode="semantic",
            ),
            "search_knowledge", cfg,
        )

    @server.tool(description="Busca híbrida (semântica + palavra-chave). O modo padrão para localizar.")
    def search_hybrid(
        query: str, limit: int = 10, lang: str | None = None,
        kind: str | None = None, path_glob: str | None = None, scope: str = "current",
    ) -> dict[str, Any]:
        return _guarded(
            lambda: api.search(
                SearchRequest(query=query, limit=limit, lang=lang, kind=kind,
                              path_glob=path_glob, scope=scope),
                mode="hybrid",
            ),
            "search_hybrid", cfg,
        )

    @server.tool(description="Metadados e lista de chunks de um documento JÁ INDEXADO (caminho relativo).")
    def get_document(path: str) -> dict[str, Any]:
        return _guarded(lambda: api.get_document(path), "get_document", cfg)

    @server.tool(description="Conteúdo completo de um chunk pelo seu id.")
    def get_chunk(chunk_id: str) -> dict[str, Any]:
        return _guarded(lambda: api.get_chunk(chunk_id), "get_chunk", cfg)

    @server.tool(description="Entidade do grafo e suas relações diretas.")
    def get_entity(name: str, depth: int = 1) -> dict[str, Any]:
        return _guarded(lambda: api.get_entity(name, depth), "get_entity", cfg)

    @server.tool(description="Busca combinando vetor e grafo: acha o que está LIGADO ao assunto.")
    def search_graph(query: str, limit: int = 10, depth: int = 1) -> dict[str, Any]:
        return _guarded(
            lambda: api.search_graph(SearchRequest(query=query, limit=limit), depth),
            "search_graph", cfg,
        )

    @server.tool(description="Monta o contexto de trabalho dentro de um orçamento de tokens.")
    def build_context(
        query: str, tokens: int = 3000, format: str = "markdown",
        include_graph: bool = True, scope: str = "current",
    ) -> dict[str, Any]:
        return _guarded(
            lambda: api.build_context(
                BuildContextRequest(
                    query=query, tokens=tokens, format=format,  # type: ignore[arg-type]
                    include_graph=include_graph, scope=scope,
                )
            ),
            "build_context", cfg,
        )

    @server.tool(description="Projetos disponíveis, integrações e divergências. Comece por aqui em ambiente multirrepositório.")
    def list_projects() -> dict[str, Any]:
        return _guarded(lambda: api.list_projects(), "list_projects", cfg)

    @server.tool(description="Contrato de um endpoint ou evento e o projeto que o provê. Funciona para projeto não clonado.")
    def get_contract(name: str, kind: str = "http") -> dict[str, Any]:
        return _guarded(lambda: api.get_contract(kind, name), "get_contract", cfg)

    @server.tool(description="Fontes de conhecimento base (@base/...) ativas nesta máquina.")
    def list_base_sources() -> dict[str, Any]:
        return _guarded(lambda: ops.base_sources(), "list_base_sources", cfg)

    # ── escrita ─────────────────────────────────────────────────────────
    # Registradas SEMPRE, mesmo em modo leitura. Uma ferramenta ausente faz o
    # agente concluir que a operação não existe; uma ferramenta que responde
    # `write_disabled` diz a verdade — existe, está desligada, eis como ligar.
    @server.tool(description="Aplica ao índice o que mudou no disco desde a última vez. Chame no INÍCIO de uma tarefa; é barato quando nada mudou.")
    def refresh() -> dict[str, Any]:
        return _guarded(lambda: ops.refresh(), "refresh", cfg)

    @server.tool(description="Reindexa o projeto. Incremental por padrão; full=true só quando chunker ou modelo de embedding mudou.")
    def reindex(full: bool = False, embed: bool = True) -> dict[str, Any]:
        return _guarded(lambda: ops.reindex(full=full, embed=embed), "reindex", cfg)

    @server.tool(description="Sincronização completa: reidrata, reindexa, reconstrói grafo e dicionário e regrava knowledge/. Operação CARA — use após mudanças estruturais.")
    def sync(full: bool = False, write_knowledge: bool = True) -> dict[str, Any]:
        return _guarded(
            lambda: ops.sync(full=full, write_knowledge=write_knowledge), "sync", cfg
        )

    @server.tool(description="Reconstrói o grafo de entidades e relações.")
    def rebuild_graph() -> dict[str, Any]:
        return _guarded(lambda: ops.rebuild_graph(), "rebuild_graph", cfg)

    @server.tool(description="Regenera o Knowledge Dictionary a partir do grafo atual.")
    def generate_dictionary() -> dict[str, Any]:
        return _guarded(lambda: ops.generate_dictionary(), "generate_dictionary", cfg)

    @server.tool(description="Instala o conhecimento base que o projeto DECLARA e falta nesta máquina. A origem vem de arquivo versionado, não do agente.")
    def base_sync() -> dict[str, Any]:
        return _guarded(lambda: ops.base_sync(), "base_sync", cfg)

    @server.tool(description="Republica a superfície pública deste projeto (rotas, eventos, clientes) no hub da máquina.")
    def publish_contract() -> dict[str, Any]:
        return _guarded(lambda: ops.publish_contract(), "publish_contract", cfg)

    # ── orquestração de tarefas (Fase 13) ───────────────────────────────
    @server.tool(description="Classifica uma solicitação: executar agora ou documentar e decompor antes. NÃO escreve nada.")
    def analyze_request(request: str) -> dict[str, Any]:
        return _guarded(lambda: orq.analyze_request(request), "analyze_request", cfg)

    @server.tool(description="Monta o plano de trabalho (documentos, tarefas, dependências). apply=true cria o projeto.")
    def plan_work(request: str, apply: bool = False) -> dict[str, Any]:
        return _guarded(lambda: orq.plan_work(request, apply), "plan_work", cfg)

    @server.tool(description="Lista tarefas, com filtro por projeto e estado.")
    def list_tasks(project_id: str | None = None, status: str | None = None, limit: int = 50) -> dict[str, Any]:
        return _guarded(lambda: orq.list_tasks(project_id, status, limit), "list_tasks", cfg)

    @server.tool(description="Detalhe de uma tarefa: critérios, escopo, dependências e último resultado.")
    def get_task(task_id: str) -> dict[str, Any]:
        return _guarded(lambda: orq.get_task(task_id), "get_task", cfg)

    @server.tool(description="O DAG de tarefas do projeto: nós e arestas.")
    def task_graph(project_id: str | None = None) -> dict[str, Any]:
        return _guarded(lambda: orq.task_graph(project_id), "task_graph", cfg)

    @server.tool(description="A próxima tarefa executável, SEM reivindicar. Use para decidir antes de pegar.")
    def next_task(project_id: str | None = None) -> dict[str, Any]:
        return _guarded(lambda: orq.next_task(project_id), "next_task", cfg)

    @server.tool(description="Painel: tarefas por estado, projetos, conhecimento e agendamentos.")
    def task_status() -> dict[str, Any]:
        return _guarded(lambda: orq.task_status(), "task_status", cfg)

    @server.tool(description="Reivindica uma tarefa com lease e devolve o CONTEXTO já montado. É assim que o agente pega trabalho.")
    def claim_task(task_id: str | None = None, project_id: str | None = None, tokens: int | None = None) -> dict[str, Any]:
        return _guarded(lambda: orq.claim_task(task_id, project_id, tokens), "claim_task", cfg)

    @server.tool(description="Entrega o resultado da tarefa. Dispara validação determinística e libera as dependentes.")
    def report_task_result(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return _guarded(lambda: orq.report_task_result(task_id, result), "report_task_result", cfg)

    @server.tool(description="Devolve uma tarefa reivindicada sem executá-la.")
    def release_task(task_id: str, reason: str = "") -> dict[str, Any]:
        return _guarded(lambda: orq.release_task(task_id, reason), "release_task", cfg)

    @server.tool(description="Muda o estado de uma tarefa (blocked, cancelled, ready...). A matriz de transições é respeitada.")
    def set_task_status(task_id: str, status: str, reason: str = "") -> dict[str, Any]:
        return _guarded(lambda: orq.set_task_status(task_id, status, reason), "set_task_status", cfg)

    @server.tool(description="Cria uma dependência entre tarefas. Ciclo é recusado com o caminho completo.")
    def add_task_dependency(task_id: str, depends_on: str, kind: str = "depends_on") -> dict[str, Any]:
        return _guarded(lambda: orq.add_task_dependency(task_id, depends_on, kind), "add_task_dependency", cfg)

    @server.tool(description="Um ciclo do worker: expira leases, promove prontas, aplica retry, dispara agendamentos. Não executa tarefa.")
    def run_worker() -> dict[str, Any]:
        return _guarded(lambda: orq.run_worker(), "run_worker", cfg)

    return server


def serve(
    project: str | None = None,
    allow_index: bool = False,
    allow_write: bool | None = None,
) -> None:
    cfg = load_config(project) if project else load_config()
    build_server(cfg, allow_index=allow_index, allow_write=allow_write).run(
        transport="stdio"
    )
