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

import functools
import time
from collections import deque
from typing import Any, Literal

from pydantic import ValidationError

from ragx.config import Config, load_config
from ragx.context.baseline import whole_files_tokens
from ragx.context.session import from_config as session_from_config
from ragx.diagnostics import log_exception, log_mcp_call, mcp_entry
from ragx.dictionary import builder as dictionary_builder
from ragx.mcp.operations import WriteAPI
from ragx.mcp.orchestration import OrchestrationAPI
from ragx.mcp.playbook import playbook, short_instructions
from ragx.mcp.tools import (
    MIN_ID_PREFIX,
    BuildContextRequest,
    SearchRequest,
    cap,
    compact,
    dump,
    err,
    ok,
    safe_echo,
    validate_path,
    wire_id,
)
from ragx.search.snippet import make_snippet


def _explain(exc: ValidationError) -> str:
    """A validação do pydantic em uma linha que diz o que corrigir.

    O `str()` de um `ValidationError` traz traceback, url de documentação e
    quebras de linha — ilegível numa caixa de erro de UI.
    """
    partes = []
    for e in exc.errors():
        campo = ".".join(str(x) for x in e["loc"]) or "argumento"
        recebido = e.get("input")
        partes.append(f"`{campo}` {e['msg'].lower()} (recebido: {recebido!r})")
    return "; ".join(partes)


def _guarded(fn: Any, tool: str, cfg: Config) -> Any:
    """Falha de ferramenta vira erro ESTRUTURADO, não exceção crua.

    Sem isto o agente recebe "Error executing tool X" — uma string sem código,
    sem causa e sem nada acionável. O detalhe vai para o log; o agente recebe
    o suficiente para decidir o que fazer.
    """
    inicio = time.monotonic()
    # Telemetria só faz sentido para um projeto de fato indexado: fora disso
    # (ver ramo `not_indexed` abaixo) toda chamada bem-sucedida deixaria uma
    # pasta `.ragx/` num diretório que nem é um projeto RAGX.
    indexado = cfg.db_path.exists()
    try:
        resultado = fn()
        if indexado:
            _log_call(cfg, tool, inicio, resultado)
        return resultado
    except ValidationError as exc:
        # Argumento fora do contrato é erro de QUEM CHAMOU, não falha interna.
        # Tratá-lo como `internal` mandava o agente (e a extensão do VS Code)
        # caçar num log de traceback o que a própria mensagem já sabe dizer:
        # qual campo, qual limite, qual valor veio. Quem recebe "ValidationError.
        # Detalhe em .ragx/logs/errors.log" não tem como corrigir a chamada.
        resposta = err("invalid_argument", f"{tool}: {_explain(exc)}")
        if indexado:
            _log_call(cfg, tool, inicio, resposta)
        return resposta
    except Exception as exc:
        # "Ainda não há índice aqui" NÃO é falha interna: é o estado normal de
        # toda pasta que não é um projeto RAGX. Com o servidor registrado
        # globalmente, isso acontece em boa parte das sessões — e responder
        # `internal` mandando olhar um log que não existe faz o agente concluir
        # que o RAGX está quebrado.
        if not indexado:
            return err(
                "not_indexed",
                f"nenhum índice em {cfg.root}. Se este é o projeto certo, rode "
                f"`ragx init && ragx index .` na raiz dele; se não, abra a "
                f"sessão dentro de um projeto já indexado.",
            )
        log_exception(cfg.state_dir, tool, exc)
        resposta = err(
            "internal",
            f"{tool} falhou: {type(exc).__name__}. "
            "Detalhe em .ragx/logs/errors.log",
        )
        _log_call(cfg, tool, inicio, resposta)
        return resposta


def _log_call(cfg: Config, tool: str, started_at: float, result: Any) -> None:
    """Telemetria de uso — uma linha por chamada, nunca a query/argumentos.

    O agente decide sozinho quando reindexar; isto é o que deixa visível,
    depois, o que ele de fato chamou e quanto cada chamada custou.
    """
    try:
        ms = round((time.monotonic() - started_at) * 1000, 1)
        # O resultado entra SEMPRE (sucesso, `ok: false`, argumento inválido, erro
        # interno), e o tamanho é o do texto que o cliente recebe, o mesmo que o
        # wrapper de `build_server` serializa (RAGX-0156).
        entry: dict[str, Any] = mcp_entry(
            tool, ms, cfg.project.name, result, dump(compact(result))
        )
        if tool == "build_context" and isinstance(result, dict) and result.get("ok"):
            data = result.get("data") or {}
            tokens = data.get("estimated_tokens")
            if isinstance(tokens, int):
                entry["tokens_delivered"] = tokens
            baseline = data.get("baseline_tokens")
            if isinstance(baseline, int):
                entry["baseline_tokens"] = baseline

        log_mcp_call(cfg.state_dir, entry, cfg.log.retain_days)
    except Exception:
        # Um bug na construção da entrada nunca pode virar `internal` para uma
        # chamada que, de resto, teve sucesso.
        pass


#: O perfil `slim` (RAGX-0157): as ferramentas que as sessões reais usam. `get_playbook` vira as
#: `instructions` (0158) e `sync` fica na CLI. Os nomes não mudam em relação ao `full`.
SLIM_TOOLS = ("get_dictionary", "search_hybrid", "build_context", "get_chunk", "get_entity", "refresh")

#: Descrições do `slim`: curtas e com a função primeiro (a descrição é custo fixo em todo turno).
_SLIM_DESCRIPTIONS = {
    "get_dictionary": "Mostra o mapa do projeto por níveis: level=0 (~700 tokens, comece aqui), 1 (~2.100), 2 (completo, ~3.800).",
    "search_hybrid": "Localiza código e docs por busca híbrida (semântica + palavra-chave): onde algo está.",
    "build_context": "Monta o contexto de uma tarefa (trechos com arquivo e linhas) dentro de um orçamento de tokens.",
    "get_chunk": "Abre o texto completo de um chunk pelo chunk_id de um resultado.",
    "get_entity": "Mostra as relações diretas de um símbolo: quem o chama e de que depende.",
    "refresh": "Reindexa o que mudou no disco (incremental). Chame no início de uma tarefa.",
}


def _slim_schema(node: Any) -> Any:
    """Tira do schema o que o modelo não usa: `title`, `default` e o `anyOf` com `null`.

    O schema exposto é só descrição: a validação dos argumentos vem da assinatura da função, então
    enxugar aqui não muda o que a ferramenta aceita. Os nomes dos parâmetros ficam, mesmo que algum
    se chame `title` ou `default` (por isso `properties` é tratado à parte).
    """
    if isinstance(node, list):
        return [_slim_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for chave, valor in node.items():
        if chave in ("title", "default"):
            continue
        if chave == "properties" and isinstance(valor, dict):
            out[chave] = {nome: _slim_schema(sub) for nome, sub in valor.items()}
        else:
            out[chave] = _slim_schema(valor)
    alternativas = out.get("anyOf")
    if isinstance(alternativas, list) and len(alternativas) == 2:
        sem_nulo = [a for a in alternativas if a != {"type": "null"}]
        if len(sem_nulo) == 1 and isinstance(sem_nulo[0], dict):
            del out["anyOf"]
            out = {**sem_nulo[0], **out}
    return out


def _slim_schemas(server: Any) -> None:
    """Aplica `_slim_schema` ao schema de entrada de cada ferramenta registrada.

    O gerenciador de ferramentas do SDK é privado (`_tool_manager`); o acesso fica isolado aqui e
    coberto por teste, porque uma mudança do SDK que o quebre deve falhar alto.
    """
    for tool in server._tool_manager.list_tools():
        novo = _slim_schema(tool.parameters)
        tool.parameters.clear()
        tool.parameters.update(novo)


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

    def __init__(self, cfg: Config, can_drain: bool = False):
        self.cfg = cfg
        # Drenar a fila de edições ESCREVE no índice: só um servidor com escrita habilitada o faz.
        self.can_drain = can_drain
        # O livro-razão vive em `ragx.context`; o servidor só segura a referência ao objeto.
        self.ledger = session_from_config(cfg)
        self.limiter = RateLimiter(cfg.mcp.rate_per_min)
        self.project = cfg.project.name or "current"

    # ── util ────────────────────────────────────────────────────────────
    def _guard(self) -> dict[str, Any] | None:
        if not self.limiter.allow():
            return err("rate_limited", f"limite de {self.limiter.per_minute} chamadas/min atingido")
        return None

    #: Quantos caminhos desatualizados a resposta lista (o resto só entra na contagem).
    _STALE_MAX = 20

    def _settle(self) -> dict[str, Any]:
        """Drena a fila de arquivos tocados e diz o que ainda pode estar desatualizado.

        Só devolve algo quando sobrou fila: sem edição pendente a resposta não ganha um byte.
        """
        from ragx.indexing.touchq import settle

        restantes = settle(self.cfg, can_drain=self.can_drain)
        if not restantes:
            return {}
        return {"stale_paths": restantes[: self._STALE_MAX], "stale_count": len(restantes)}

    def _detailed(self, fmt: str | None) -> bool:
        return (fmt or self.cfg.mcp.response_format) == "detailed"

    def _hit(self, r: Any, detailed: bool = True) -> dict[str, Any]:
        # Sem `project` por hit: ele vai UMA vez em `data.project` (a busca federada
        # o acrescenta de volta, porque lá cada hit tem a sua origem). Nulos somem no
        # fio (`compact`) e o score tem 4 casas: o resto era ruído em cada um dos 10 hits.
        return {
            "chunk_id": wire_id(r.chunk_id),
            "document_path": r.document_path,
            "symbol": r.symbol,
            "heading_path": r.heading_path,
            "kind": r.kind.value,
            "lines": [r.start_line, r.end_line],
            "score": round(r.score, 4),
            # `concise` (o padrão da busca): um trecho curto, não o conteúdo inteiro. O
            # agente abre o trecho completo com `get_chunk`.
            **(
                {"content": r.content}
                if detailed
                else {"snippet": make_snippet(r.content, self.cfg.mcp.snippet_chars)}
            ),
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

        if req.scope != "current":
            # `scope` era aceito e ignorado: `all` consultava só o projeto atual
            return self._search_scoped(req, mode, path_glob)

        stale = self._settle()
        out = run(
            self.cfg, req.query, mode=mode, limit=req.limit,
            filters=SearchFilters(lang=req.lang, kind=req.kind, path_glob=path_glob),
        )
        return cap(
            ok(
                {
                    "project": self.project,
                    "mode": out.mode,
                    "degraded": out.degraded,
                    # só aparece quando existe: não acrescenta `null` ao fio
                    **({"partial": out.partial} if out.partial else {}),
                    **stale,
                    "results": [self._hit(r, self._detailed(req.response_format)) for r in out.results],
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

    def list_documents(
        self, path_glob: str | None = None, lang: str | None = None,
        kind: str | None = None, limit: int = 200,
    ) -> dict[str, Any]:
        """Inventário do que está indexado. METADADO, nunca conteúdo.

        Existe para responder "o que exatamente há neste índice, e de qual
        origem". Sem isto, a única forma de listar documentos pelo MCP era
        deduzir os caminhos dos resultados de uma busca — o que devolve o que
        casa com a consulta, não o que existe, e nunca o que tem zero relevância
        para ela.

        A separação por origem sai do próprio caminho: `@base/<fonte>/…` é
        conhecimento compartilhado, o resto é deste repositório.
        """
        blocked = self._guard()
        if blocked:
            return blocked

        from ragx.storage.db import open_db
        from ragx.storage.repositories import DocumentRepo

        teto = max(1, min(int(limit), 2000))
        # O repositório recebe um LIKE. Quem chama pensa em prefixo ou trecho de
        # caminho, não em SQL — traduzir aqui evita a busca que devolve vazio
        # em silêncio porque faltou um `%`.
        padrao = None
        if path_glob:
            padrao = path_glob if "*" in path_glob or "%" in path_glob else f"*{path_glob}*"

        with open_db(self.cfg.db_path, read_only=True) as conn:
            linhas = DocumentRepo(conn).list(
                lang=lang, kind=kind, path_like=padrao, limit=teto
            )

        documentos = [
            {
                "path": d["rel_path"], "lang": d["lang"], "kind": d["doc_kind"],
                "title": d["title"], "redacted": bool(d["redacted"]),
                "size_bytes": d["size_bytes"],
            }
            for d in linhas
        ]
        por_origem: dict[str, int] = {}
        for d in documentos:
            caminho = d["path"]
            origem = (
                f"@base/{caminho.split('/')[1]}"
                if caminho.startswith("@base/") and "/" in caminho[6:]
                else self.project
            )
            por_origem[origem] = por_origem.get(origem, 0) + 1

        return cap(
            ok({
                "project": self.project,
                "documents": documentos,
                "count": len(documentos),
                "by_source": por_origem,
                "truncated": len(documentos) >= teto,
            }),
            self.cfg.mcp.max_response_bytes,
        )

    def get_chunk(self, chunk_id: str) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        if not chunk_id or len(chunk_id) > 64:
            return err("invalid_id", "chunk_id inválido")
        eh_hex = all(c in "0123456789abcdef" for c in chunk_id.lower())
        if not eh_hex or len(chunk_id) < MIN_ID_PREFIX:
            return err(
                "invalid_id",
                f"chunk_id é hexadecimal, com no mínimo {MIN_ID_PREFIX} caracteres "
                "(o fio traz 12; o id completo tem 32)",
            )

        from ragx.storage.db import open_db
        from ragx.storage.repositories import ChunkRepo

        with open_db(self.cfg.db_path, read_only=True) as conn:
            repo = ChunkRepo(conn)
            if len(chunk_id) == 32:
                row = repo.get(chunk_id.lower())
                ambiguo = False
            else:
                row, ambiguo = repo.get_by_prefix(chunk_id.lower())
            if ambiguo:
                return err(
                    "invalid_id",
                    f"prefixo ambíguo: mais de um chunk começa com {safe_echo(chunk_id)}; "
                    "use mais caracteres",
                )
            if row is None:
                return err("not_found", f"chunk não encontrado: {safe_echo(chunk_id)}")
        if self.ledger is not None:  # abrir um chunk o torna "entregue", mas aqui o conteúdo vai SEMPRE inteiro
            self.ledger.mark(row["id"], row["rel_path"], row["start_line"], row["end_line"],
                             int(row["token_count"] or 0))
        return ok(
            {
                "project": self.project,
                "chunk_id": wire_id(row["id"]),
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
        from ragx.graph.store import GraphStore, confidence_tier
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
                        "source": target["source"],
                        "tier": confidence_tier(target["confidence"]),
                    },
                    # Cada relação carrega a aresta ORIENTADA (`src`/`dst`, os
                    # mesmos nomes da tabela `relations`) e o nó do outro lado
                    # (`other*`), que é o que uma lista de vizinhos quer ler.
                    # Entregar só `other` obrigava o cliente a reconstruir a
                    # direção — e o grafo do VS Code, que não reconstruía,
                    # ficava sem nenhuma aresta. Ver docs/06-grafo.md.
                    "relations": [
                        {
                            "direction": e["direction"], "type": e["type"],
                            "src": e["src_id"], "dst": e["dst_id"],
                            "other": e["other_name"], "other_id": e["other_id"],
                            "other_type": e["other_type"],
                            "other_qualified_name": e["other_qname"],
                            "weight": e["weight"],
                            "confidence": e["confidence"],
                            "source": e["source"],
                            "tier": confidence_tier(e["confidence"]),
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

        stale = self._settle()
        out = graph_search(
            self.cfg, req.query, limit=req.limit, depth=min(max(depth, 1), 2),
            filters=SearchFilters(lang=req.lang),
        )
        return cap(
            ok(
                {
                    "project": self.project,
                    "seeds": out.seeds,
                    "expanded": len(out.expansion.scores),
                    "truncated": out.expansion.truncated,
                    **stale,
                    "results": [
                        {**self._hit(r, self._detailed(req.response_format)), "via": r.metadata.get("via", "graph")}
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

        project = self.project
        other_cfg: Config | None = None
        stale: dict[str, Any] = {}
        # Teto: o pedido acima dele é limitado E informado (`tokens_capped`), nunca cortado
        # em silêncio. `BuildContextRequest.tokens` continua validando até MAX_TOKENS.
        teto = self.cfg.mcp.max_context_tokens
        budget = min(req.tokens, teto)
        if req.scope != "current":
            from ragx.core.errors import UsageError
            from ragx.federation.context import (
                ScopeNotFoundError,
                ScopeUnsupportedError,
                build_scoped_context,
            )

            try:
                pack, project, used_cfg = build_scoped_context(
                    self.cfg, req.scope, req.query, budget, req.include_graph
                )
            except ScopeNotFoundError as exc:
                return err("not_found", str(exc).splitlines()[0])
            except ScopeUnsupportedError as exc:
                return err("scope_unsupported", str(exc).splitlines()[0])
            except UsageError as exc:
                return err("invalid_scope", str(exc).splitlines()[0])
            other_cfg = None if used_cfg is self.cfg else used_cfg
        else:
            stale = self._settle()
            pack = run(
                self.cfg, req.query, budget=budget, include_graph=req.include_graph
            )
            # chunk já entregue nesta sessão volta como referência (RAGX-0159)
            from ragx.context.engine import apply_session

            pack = apply_session(pack, self.ledger)
        payload: dict[str, Any] = {
            "project": project,
            "estimated_tokens": pack.estimated_tokens,
            "budget": pack.budget,
            "sources": list(pack.sources),
            **stale,
        }
        if req.tokens > teto:
            payload["tokens_capped"] = teto
        # UMA representação do conteúdo, nunca duas: o markdown e os fragmentos
        # carregavam o mesmo texto, e um pedido de 3.000 tokens chegava a ~8.000
        # (RAGX-0154). `estimated_tokens` conta o markdown que sai, sem o título.
        if pack.references:
            payload["dedupe_refs"] = len(pack.references)
            payload["dedupe_saved_tokens"] = pack.stats.get("dedupe_saved_tokens", 0)
        if req.format == "json":
            if pack.references:
                payload["references"] = [
                    {"chunk_id": wire_id(r.chunk_id), "document_path": r.document_path,
                     "lines": [r.start_line, r.end_line]}
                    for r in pack.references
                ]
            payload["fragments"] = [
                {
                    "project": project if req.scope != "current" else f.project,
                    "chunk_id": wire_id(f.chunk_id),
                    "document_path": f.document_path,
                    "lines": [f.start_line, f.end_line],
                    "symbol": f.symbol,
                    "heading_path": f.heading_path,
                    "compressed": f.compressed,
                    "tokens": f.tokens,
                    "content": f.content,
                }
                for f in pack.fragments
            ]
        else:
            payload["markdown"] = render(pack, "markdown", title=False)
        if self._detailed(req.response_format):
            # `detailed`: o que serve para depurar a montagem do contexto, SEM o conteúdo
            # (que já está no markdown).
            motivos: dict[str, int] = {}
            for _cid, why in pack.dropped:
                chave = why.split(":")[0]
                motivos[chave] = motivos.get(chave, 0) + 1
            payload["intent"] = pack.intent
            payload["dropped"] = motivos
            payload["stats"] = pack.stats
            payload["fragments_meta"] = [
                {
                    "chunk_id": wire_id(f.chunk_id),
                    "lines": [f.start_line, f.end_line],
                    "tokens": f.tokens,
                    "strategy": f.strategy,
                    "reason": f.reason,
                    "score": round(f.score, 4),
                }
                for f in pack.fragments
            ]
        payload["baseline_tokens"] = whole_files_tokens(other_cfg or self.cfg, pack.sources)
        return cap(ok(payload), self.cfg.mcp.max_response_bytes)

    def get_dictionary(self, section: str | None = None, level: int = 2) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        data = dictionary_builder.load(self.cfg)
        if data is None:
            try:
                data, _ = dictionary_builder.build(self.cfg)
            except Exception:
                return err("not_found", "dicionário indisponível: rode `ragx dictionary generate`")
        if level not in dictionary_builder.LEVELS:
            return err("invalid_argument", f"level deve ser 0, 1 ou 2 (recebi {safe_echo(str(level), 12)})")
        # `section` escolhe a seção do dicionário COMPLETO; `level` recorta o que vem dela (e, sem `section`, o todo)
        if section:
            if section not in data:
                return err(
                    "not_found",
                    f"seção desconhecida: {safe_echo(section, 40)} (disponíveis: {', '.join(sorted(data))})",
                )
            visto = dictionary_builder.at_level(data, level)
            data = {section: visto.get(section, data[section] if level >= 2 else [])}
        else:
            data = dictionary_builder.at_level(data, level)
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
        path_glob = None
        if req.path_glob:
            path_glob = validate_path(req.path_glob)
            if path_glob is None:
                return err("invalid_path", "path_glob não pode ser absoluto nem conter '..'")
        return self._search_scoped(req, mode, path_glob)

    def _search_scoped(self, req: SearchRequest, mode: str, path_glob: str | None) -> dict[str, Any]:
        from ragx.federation.search import search_scoped as run
        from ragx.search.service import SearchFilters

        try:
            out = run(
                self.cfg, req.query, scope=req.scope, mode=mode, limit=req.limit,
                filters=SearchFilters(lang=req.lang, kind=req.kind, path_glob=path_glob),
            )
        except Exception as exc:
            return err("invalid_scope", str(exc).splitlines()[0])
        if not out.found:
            # Projeto privado ou inexistente: a MESMA resposta, de propósito.
            target = req.scope.split(":", 1)[1] if ":" in req.scope else req.scope
            return err("not_found", f"projeto não encontrado: {target}")
        return cap(
            ok(
                {
                    "mode": mode, "scope": req.scope,
                    "projects": out.projects,
                    "degraded": out.degraded or None,
                    "results": [
                        {**self._hit(r, self._detailed(req.response_format)), "project": r.project}
                        for r in out.results
                    ],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )


def build_server(
    cfg: Config,
    allow_index: bool = False,
    allow_write: bool | None = None,
    profile: str | None = None,
) -> Any:
    from mcp.server.mcpserver import MCPServer

    write_enabled = cfg.mcp.allow_write if allow_write is None else allow_write
    perfil = profile or cfg.mcp.profile
    api = KnowledgeAPI(cfg, can_drain=write_enabled)
    ops = WriteAPI(cfg, enabled=write_enabled)
    orq = OrchestrationAPI(cfg, enabled=write_enabled)
    server = MCPServer(
        name="ragx",
        instructions=short_instructions(write_enabled, perfil),
    )

    def _tool(description: str) -> Any:
        """Registra a ferramenta devolvendo TEXTO JSON compacto.

        Sem isto o SDK reindenta o `dict` (`indent=2`), o repete em
        `structuredContent` e anexa um `outputSchema` a cada ferramenta: tudo isso
        é custo em tokens para o agente e nada para o modelo. `_guarded` continua
        devolvendo `dict` (é o que os testes e a CLI chamam); o texto é montado
        aqui, uma vez, na borda (RAGX-0155).
        """
        def deco(fn: Any) -> Any:
            nonlocal description
            if perfil == "slim":
                if fn.__name__ not in SLIM_TOOLS:
                    return fn  # fora do perfil: a função continua existindo, só não é registrada
                description = _SLIM_DESCRIPTIONS.get(fn.__name__, description)

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                return dump(compact(fn(*args, **kwargs)))

            server.tool(description=description, structured_output=False)(wrapper)
            return fn

        return deco

    @_tool(description="Ensina a operar o RAGX: ordem das ferramentas, quando reindexar e o que o índice não faz. Leia uma vez, no início da sessão.")
    def get_playbook() -> dict[str, Any]:
        return _guarded(
            lambda: ok({**playbook(cfg, write_enabled), "response_format": 2}),
            "get_playbook", cfg,
        )

    @_tool(description="Mostra o mapa do projeto por níveis: level=0 (~700 tokens, comece aqui), 1 (~2.100), 2 (completo, ~3.800, o padrão). Use primeiro, para se orientar.")
    def get_dictionary(section: str | None = None, level: int = 2) -> dict[str, Any]:
        return _guarded(lambda: api.get_dictionary(section, level), "get_dictionary", cfg)

    @_tool(description="Busca por significado (semântica) no conhecimento indexado. Para localizar também por palavra-chave, prefira search_hybrid.")
    def search_knowledge(
        query: str, limit: int = 10, lang: str | None = None,
        kind: str | None = None, path_glob: str | None = None, scope: str = "current",
        response_format: Literal["concise", "detailed"] | None = None,
    ) -> dict[str, Any]:
        return _guarded(
            lambda: api.search(
                SearchRequest(query=query, limit=limit, lang=lang, kind=kind,
                              path_glob=path_glob, scope=scope,
                              response_format=response_format),
                mode="semantic",
            ),
            "search_knowledge", cfg,
        )

    @_tool(description="Localiza código e documentação por busca híbrida (semântica + palavra-chave): onde algo está, o que trata de X. O modo padrão para localizar.")
    def search_hybrid(
        query: str, limit: int = 10, lang: str | None = None,
        kind: str | None = None, path_glob: str | None = None, scope: str = "current",
        response_format: Literal["concise", "detailed"] | None = None,
    ) -> dict[str, Any]:
        return _guarded(
            lambda: api.search(
                SearchRequest(query=query, limit=limit, lang=lang, kind=kind,
                              path_glob=path_glob, scope=scope,
                              response_format=response_format),
                mode="hybrid",
            ),
            "search_hybrid", cfg,
        )

    @_tool(description="Lista os chunks e os metadados de um documento já indexado, pelo caminho relativo. Não lê o arquivo do disco.")
    def get_document(path: str) -> dict[str, Any]:
        return _guarded(lambda: api.get_document(path), "get_document", cfg)

    @_tool(description="Lista os documentos indexados e de que origem vêm (@base/... é conhecimento compartilhado). Só metadado, sem conteúdo.")
    def list_documents(
        path_glob: str | None = None, lang: str | None = None,
        kind: str | None = None, limit: int = 200,
    ) -> dict[str, Any]:
        return _guarded(
            lambda: api.list_documents(path_glob, lang, kind, limit), "list_documents", cfg,
        )

    @_tool(description="Abre o texto completo de um chunk pelo chunk_id de um resultado de busca.")
    def get_chunk(chunk_id: str) -> dict[str, Any]:
        return _guarded(lambda: api.get_chunk(chunk_id), "get_chunk", cfg)

    @_tool(description="Mostra as relações diretas de um símbolo do grafo: quem o chama, quem ele chama e de que depende.")
    def get_entity(name: str, depth: int = 1) -> dict[str, Any]:
        return _guarded(lambda: api.get_entity(name, depth), "get_entity", cfg)

    @_tool(description="Localiza o que está ligado a um assunto combinando vetor e grafo: quem chama, depende ou documenta o resultado.")
    def search_graph(query: str, limit: int = 10, depth: int = 1) -> dict[str, Any]:
        return _guarded(
            lambda: api.search_graph(SearchRequest(query=query, limit=limit), depth),
            "search_graph", cfg,
        )

    @_tool(description="Monta o contexto de trabalho de uma tarefa (trechos com arquivo e linhas) dentro de um orçamento de tokens.")
    def build_context(
        query: str, tokens: int = 3000, format: str = "markdown",
        include_graph: bool = True, scope: str = "current",
        response_format: Literal["concise", "detailed"] | None = None,
    ) -> dict[str, Any]:
        return _guarded(
            lambda: api.build_context(
                BuildContextRequest(
                    query=query, tokens=tokens, format=format,  # type: ignore[arg-type]
                    include_graph=include_graph, scope=scope,
                    response_format=response_format,
                )
            ),
            "build_context", cfg,
        )

    @_tool(description="Lista os projetos disponíveis, integrações e divergências. Use primeiro em ambiente multirrepositório.")
    def list_projects() -> dict[str, Any]:
        return _guarded(lambda: api.list_projects(), "list_projects", cfg)

    @_tool(description="Mostra o contrato de um endpoint ou evento e o projeto que o provê. Funciona para projeto não clonado.")
    def get_contract(name: str, kind: str = "http") -> dict[str, Any]:
        return _guarded(lambda: api.get_contract(kind, name), "get_contract", cfg)

    @_tool(description="Lista as fontes de conhecimento base (@base/...) ativas nesta máquina.")
    def list_base_sources() -> dict[str, Any]:
        return _guarded(lambda: ops.base_sources(), "list_base_sources", cfg)

    # ── escrita ─────────────────────────────────────────────────────────
    # Registradas SEMPRE, mesmo em modo leitura. Uma ferramenta ausente faz o
    # agente concluir que a operação não existe; uma ferramenta que responde
    # `write_disabled` diz a verdade — existe, está desligada, eis como ligar.
    @_tool(description="Reindexa o que mudou no disco (incremental, ~1 s sem mudança). Chame no início de uma tarefa. Não regrava knowledge/ (isso é sync).")
    def refresh() -> dict[str, Any]:
        return _guarded(lambda: ops.refresh(), "refresh", cfg)

    @_tool(description="Reindexa o projeto. Incremental por padrão; use full=true só quando o chunker ou o modelo de embedding mudou.")
    def reindex(full: bool = False, embed: bool = True) -> dict[str, Any]:
        return _guarded(lambda: ops.reindex(full=full, embed=embed), "reindex", cfg)

    @_tool(description="Sincroniza tudo: reidrata, reindexa, reconstrói grafo e dicionário e regrava knowledge/. Operação cara: use após mudanças estruturais.")
    def sync(full: bool = False, write_knowledge: bool = True) -> dict[str, Any]:
        return _guarded(
            lambda: ops.sync(full=full, write_knowledge=write_knowledge), "sync", cfg
        )

    @_tool(description="Reconstrói o grafo de entidades e relações.")
    def rebuild_graph() -> dict[str, Any]:
        return _guarded(lambda: ops.rebuild_graph(), "rebuild_graph", cfg)

    @_tool(description="Regenera o Knowledge Dictionary a partir do grafo atual.")
    def generate_dictionary() -> dict[str, Any]:
        return _guarded(lambda: ops.generate_dictionary(), "generate_dictionary", cfg)

    @_tool(description="Instala o conhecimento base que o projeto declara e falta nesta máquina. A origem vem de arquivo versionado, não do agente.")
    def base_sync() -> dict[str, Any]:
        return _guarded(lambda: ops.base_sync(), "base_sync", cfg)

    @_tool(description="Republica a superfície pública deste projeto (rotas, eventos, clientes) no hub da máquina.")
    def publish_contract() -> dict[str, Any]:
        return _guarded(lambda: ops.publish_contract(), "publish_contract", cfg)

    # ── orquestração de tarefas (Fase 13) ───────────────────────────────
    @_tool(description="Classifica uma solicitação: executar agora ou documentar e decompor antes. Não escreve nada.")
    def analyze_request(request: str) -> dict[str, Any]:
        return _guarded(lambda: orq.analyze_request(request), "analyze_request", cfg)

    @_tool(description="Monta o plano de trabalho (documentos, tarefas, dependências). Com apply=true, cria o projeto.")
    def plan_work(request: str, apply: bool = False) -> dict[str, Any]:
        return _guarded(lambda: orq.plan_work(request, apply), "plan_work", cfg)

    @_tool(description="Lista tarefas, com filtro por projeto e estado.")
    def list_tasks(project_id: str | None = None, status: str | None = None, limit: int = 50) -> dict[str, Any]:
        return _guarded(lambda: orq.list_tasks(project_id, status, limit), "list_tasks", cfg)

    @_tool(description="Mostra o detalhe de uma tarefa: critérios, escopo, dependências e último resultado.")
    def get_task(task_id: str) -> dict[str, Any]:
        return _guarded(lambda: orq.get_task(task_id), "get_task", cfg)

    @_tool(description="Mostra o DAG de tarefas do projeto: nós e arestas.")
    def task_graph(project_id: str | None = None) -> dict[str, Any]:
        return _guarded(lambda: orq.task_graph(project_id), "task_graph", cfg)

    @_tool(description="Indica a próxima tarefa executável, sem reivindicá-la. Use para decidir antes de pegar.")
    def next_task(project_id: str | None = None) -> dict[str, Any]:
        return _guarded(lambda: orq.next_task(project_id), "next_task", cfg)

    @_tool(description="Mostra o painel: tarefas por estado, projetos, conhecimento e agendamentos.")
    def task_status() -> dict[str, Any]:
        return _guarded(lambda: orq.task_status(), "task_status", cfg)

    @_tool(description="Reivindica uma tarefa com lease e devolve o contexto já montado. É assim que o agente pega trabalho.")
    def claim_task(task_id: str | None = None, project_id: str | None = None, tokens: int | None = None) -> dict[str, Any]:
        return _guarded(lambda: orq.claim_task(task_id, project_id, tokens), "claim_task", cfg)

    @_tool(description="Entrega o resultado da tarefa. Dispara a validação determinística e libera as dependentes.")
    def report_task_result(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return _guarded(lambda: orq.report_task_result(task_id, result), "report_task_result", cfg)

    @_tool(description="Devolve uma tarefa reivindicada sem executá-la.")
    def release_task(task_id: str, reason: str = "") -> dict[str, Any]:
        return _guarded(lambda: orq.release_task(task_id, reason), "release_task", cfg)

    @_tool(description="Muda o estado de uma tarefa (blocked, cancelled, ready...), respeitando a matriz de transições.")
    def set_task_status(task_id: str, status: str, reason: str = "") -> dict[str, Any]:
        return _guarded(lambda: orq.set_task_status(task_id, status, reason), "set_task_status", cfg)

    @_tool(description="Cria uma dependência entre tarefas. Ciclo é recusado, com o caminho completo.")
    def add_task_dependency(task_id: str, depends_on: str, kind: str = "depends_on") -> dict[str, Any]:
        return _guarded(lambda: orq.add_task_dependency(task_id, depends_on, kind), "add_task_dependency", cfg)

    @_tool(description="Roda um ciclo do worker: expira leases, promove prontas, aplica retry, dispara agendamentos. Não executa tarefa.")
    def run_worker() -> dict[str, Any]:
        return _guarded(lambda: orq.run_worker(), "run_worker", cfg)

    if perfil == "slim":
        _slim_schemas(server)
    return server


def serve(
    project: str | None = None,
    allow_index: bool = False,
    allow_write: bool | None = None,
    profile: str | None = None,
) -> None:
    cfg = load_config(project) if project else load_config()
    server = build_server(cfg, allow_index=allow_index, allow_write=allow_write, profile=profile)
    from ragx.mcp.warmup import start

    start(cfg)  # em segundo plano: não atrasa o `initialize`
    server.run(transport="stdio")
