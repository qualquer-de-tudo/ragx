"""`build_context` de OUTRO projeto do hub (`scope="project:<nome>"`).

O servidor MCP só valida e serializa; resolver o projeto, aplicar a visibilidade
e montar o pack com a configuração DELE é daqui. As regras são as de
`federation/search.py`:

- projeto `private` ou inexistente: indistinguíveis de propósito (mesmo erro,
  e nenhum banco é aberto antes de recusar);
- a visibilidade que vale é a do `ragx.toml` LIVE do outro projeto, não a que o
  hub guardou no passado;
- projeto sem clone local (só federação) só tem contratos: não há índice para
  montar contexto.

`scope="all"` não é suportado: modelos de embedding diferentes não se combinam
num mesmo pack, e fingir que combinam produziria ranking com aparência de
resultado.

Ver docs/17-multiprojeto-e-federacao.md.
"""

from __future__ import annotations

from ragx.config import Config, load_config
from ragx.context.engine import ContextPack, build_context
from ragx.core.errors import UsageError
from ragx.federation.hub import hub_db, list_projects
from ragx.federation.search import parse_scope, raise_no_hub


class ScopeNotFoundError(UsageError):
    """Projeto inexistente OU privado: a mensagem não diferencia os dois."""


class ScopeUnsupportedError(UsageError):
    """O escopo é válido, mas não dá para montar contexto dele."""


def build_scoped_context(
    cfg: Config, scope: str, query: str, budget: int, include_graph: bool
) -> tuple[ContextPack, str, Config]:
    """(pack, nome do projeto, config usada). Levanta `ScopeNotFoundError`, `ScopeUnsupportedError` ou `UsageError`."""
    kind, target = parse_scope(scope)
    current = cfg.project.name or "current"

    if kind == "all":
        raise ScopeUnsupportedError(
            "build_context só combina um projeto por vez; use project:<nome> "
            'ou search_hybrid(scope="all")'
        )
    if kind == "current" or target == current:
        if cfg.project.visibility == "private" and kind != "current":
            raise ScopeNotFoundError(f"projeto não encontrado: {target}")
        pack = build_context(cfg, query, budget=budget, include_graph=include_graph)
        return pack, current, cfg

    assert target is not None
    if not hub_db(cfg).exists():
        raise_no_hub()
    alvo = next(
        (p for p in list_projects(cfg) if p["name"] == target and p["visibility"] != "private"),
        None,
    )
    if alvo is None:
        raise ScopeNotFoundError(f"projeto não encontrado: {target}")
    if not (alvo["cloned"] and alvo["path"]):
        raise ScopeUnsupportedError(
            f"{target} não tem clone local: só os contratos dele estão disponíveis "
            "(get_contract / search_hybrid); não há índice para montar contexto"
        )
    try:
        other = load_config(alvo["path"])
    except Exception as exc:
        raise ScopeUnsupportedError(f"configuração de {target} ilegível") from exc
    if other.project.visibility == "private":
        # o hub pode estar velho: a config LIVE manda
        raise ScopeNotFoundError(f"projeto não encontrado: {target}")
    if not other.db_path.exists():
        raise ScopeUnsupportedError(f"{target} não tem índice local (rode `ragx index` lá)")
    pack = build_context(other, query, budget=budget, include_graph=include_graph)
    return pack, target, other
