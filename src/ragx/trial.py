"""`ragx trial` — quanto contexto o RAGX poupa, em tokens, como ESTIMATIVA.

Leia isto antes de citar qualquer número que este módulo produz.

O que ele compara:

    build_context(pergunta)          ← os trechos que o RAGX selecionou
        contra
    o texto inteiro dos arquivos     ← o que seria lido sem o RAGX

O que ele **não** é:

- **Não é a conta do seu provedor.** Tokens aqui são contados por
  `ragx.tokens`, com `tiktoken` quando disponível e uma heurística quando não.
  Nenhum dos dois é o tokenizador do modelo que você usa. Modelos diferentes
  tokenizam o mesmo texto de formas diferentes.
- **Não é economia garantida.** Ele mede o tamanho de duas entradas possíveis.
  Não mede se a menor delas foi SUFICIENTE para a tarefa. Contexto que falta
  gera pergunta de novo, e uma segunda volta pode custar mais do que a leitura
  inteira teria custado.
- **Não é a sua sessão real.** Um agente de verdade não lê o repositório
  inteiro nem lê um arquivo por completo toda vez: ele busca, abre pedaços,
  desiste. O basal aqui é um limite superior grosseiro, não o comportamento
  observado de ninguém.

Por que ainda assim vale medir: a ordem de grandeza é informativa. Saber que um
contexto de 3 mil tokens substitui a leitura de 40 mil ajuda a decidir; achar
que isso são 37 mil tokens a menos na fatura, não.

Por isso toda saída deste módulo carrega o aviso junto, e os campos se chamam
`estimated_*`. Ver `docs/07-context-engine.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ragx.config import Config
from ragx.core.models import Verdict
from ragx.tokens import count_tokens, get_counter

#: O aviso vai junto do número, em toda saída. Separar os dois é como uma
#: estimativa vira "o RAGX economiza 94%" num slide.
RESSALVA = (
    "ESTIMATIVA, não medição de consumo real. Os tokens são contados por um "
    "tokenizador aproximado, e o basal supõe leitura integral dos arquivos — "
    "que não é como um agente realmente trabalha. Serve para ordem de "
    "grandeza; não serve para prever fatura."
)


@dataclass
class Basal:
    """O lado 'ler tudo' da comparação."""

    #: Arquivos efetivamente lidos e contados.
    files: int = 0
    tokens: int = 0
    bytes_read: int = 0
    empty_files: int = 0
    #: Arquivos que existem mas NÃO entraram na conta, por motivo.
    excluded: dict[str, int] = field(default_factory=dict)

    def _excluir(self, motivo: str) -> None:
        self.excluded[motivo] = self.excluded.get(motivo, 0) + 1


@dataclass
class Trial:
    query: str
    budget: int
    scope: str
    counter: str
    context_tokens: int
    context_fragments: int
    context_sources: int
    baseline: Basal

    @property
    def saved_tokens(self) -> int:
        """Diferença bruta. Pode ser NEGATIVA — e quando é, dizer isso importa."""
        return self.baseline.tokens - self.context_tokens

    @property
    def saved_ratio(self) -> float | None:
        """Fração poupada, ou `None` quando não há basal para comparar.

        Devolver 0.0 num basal vazio afirmaria "não poupou nada", quando a
        verdade é "não houve o que comparar".
        """
        if self.baseline.tokens <= 0:
            return None
        return self.saved_tokens / self.baseline.tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "disclaimer": RESSALVA,
            "is_estimate": True,
            "query": self.query,
            "scope": self.scope,
            "token_counter": self.counter,
            "context": {
                "estimated_tokens": self.context_tokens,
                "fragments": self.context_fragments,
                "sources": self.context_sources,
                "budget": self.budget,
            },
            "baseline_full_read": {
                "estimated_tokens": self.baseline.tokens,
                "files": self.baseline.files,
                "bytes": self.baseline.bytes_read,
                "empty_files": self.baseline.empty_files,
                "excluded": dict(sorted(self.baseline.excluded.items())),
            },
            "estimated_savings": {
                "tokens": self.saved_tokens,
                "ratio": None if self.saved_ratio is None else round(self.saved_ratio, 4),
                "comparable": self.baseline.tokens > 0,
            },
        }


def _contar_arquivos(
    cfg: Config, caminhos: list[str] | None, globs: list[str] | None = None
) -> Basal:
    """Conta os tokens da leitura integral, passando pelo MESMO gate do índice.

    Duas decisões que mudam o número, e por isso ficam explícitas:

    1. **Arquivo bloqueado não é lido nem contado.** Contar um `.env` no basal
       inflaria a economia com tokens que o RAGX jamais serviria — e exigiria
       ler o segredo para contá-lo, que é precisamente o que o projeto existe
       para não fazer.
    2. **Arquivo grande demais é excluído, não truncado.** Truncar inventaria
       um número; excluir SUBESTIMA a economia, que é o lado seguro do erro.

    Os dois casos vão para `excluded`, com contagem, para que o número possa
    ser interpretado em vez de apenas citado.
    """
    from ragx.security.gate import SecurityGate
    from ragx.walk import iter_files

    gate = SecurityGate(
        cfg.root,
        policy=cfg.security.policy,
        extra_exclude=list(cfg.index.exclude),
        extra_include=list(cfg.index.include),
    )
    # Conhecimento base (`@base/...`) mora fora da raiz do projeto: o walker
    # nunca o emite. Contá-lo como "não encontrado" sugeriria arquivo sumido,
    # quando o certo é dizer que ele não faz parte deste basal.
    externos = [c for c in caminhos or [] if c.startswith("@")]
    internos = [c for c in caminhos or [] if not c.startswith("@")]

    basal = Basal()
    for _ in externos:
        basal._excluir("outside_project_root")

    if caminhos is not None and not internos:
        # Todas as fontes eram externas: não há o que varrer na raiz.
        return basal
    alvo = set(internos) if caminhos is not None else None

    casou: set[str] = set()
    for f in iter_files(cfg.root, gate, max_bytes=cfg.index.max_file_bytes, only=alvo):
        if globs and not matches(f.rel_path, globs):
            continue
        casou.add(f.rel_path)
        verdict = f.decision.verdict
        if verdict is Verdict.BLOCK:
            basal._excluir("blocked_by_security_gate")
            continue
        if verdict is Verdict.SKIP:
            # Binário, indecifrável ou coberto por .gitignore/.ragignore.
            basal._excluir(f.decision.rule_id or "skipped")
            continue

        conteudo = f.content
        if conteudo is None:
            basal._excluir("unreadable")
            continue
        if not conteudo.strip():
            # Arquivo vazio é um arquivo lido: conta como leitura, com 0 tokens.
            basal.empty_files += 1

        basal.files += 1
        basal.bytes_read += f.size_bytes
        basal.tokens += count_tokens(conteudo)

    if alvo:
        # Caminho pedido que o walker nunca emitiu: não existe mais no disco.
        # Silenciar isso faria o basal parecer menor sem explicação.
        vistos = basal.files + sum(
            n for motivo, n in basal.excluded.items() if motivo != "outside_project_root"
        )
        for _ in range(max(0, len(alvo) - vistos)):
            basal._excluir("not_found")

    return basal


def run(
    cfg: Config,
    query: str,
    tokens: int = 3000,
    scope: str = "sources",
    paths: list[str] | None = None,
    globs: list[str] | None = None,
) -> Trial:
    """Monta o contexto e compara com a leitura integral.

    `scope`:

    - `sources` — só os arquivos de onde o contexto saiu. É a comparação
      defensável: "você teria aberto estes arquivos".
    - `project` — o projeto indexado inteiro. É o basal do "joga tudo no
      contexto", útil como teto e enganoso como promessa.

    `paths` fixa os caminhos exatos; `globs` filtra a varredura por padrão.
    Os dois passam pelo mesmo walker, então nenhum deles alcança arquivo que o
    RAGX não serviria.
    """
    from ragx.context.engine import build_context

    pack = build_context(cfg, query, budget=tokens)

    if paths:
        alvo: list[str] | None = list(paths)
    elif globs:
        alvo = None  # varre a raiz, filtrando por padrão
    elif scope == "sources":
        alvo = list(pack.sources)
    else:
        alvo = None

    # `sources` sem nenhuma fonte: o contexto veio vazio. Varrer o projeto
    # inteiro nesse caso trocaria a pergunta e produziria uma economia enorme
    # e sem sentido.
    if (paths is not None and not paths and not globs) or (scope == "sources" and not globs and not paths and not pack.sources):
        basal = Basal()
    else:
        basal = _contar_arquivos(cfg, alvo, globs)

    return Trial(
        query=query,
        budget=tokens,
        scope="paths" if (paths or globs) else scope,
        counter=get_counter().name,
        context_tokens=pack.estimated_tokens,
        context_fragments=len(pack.fragments),
        context_sources=len(pack.sources),
        baseline=basal,
    )


def matches(rel_path: str, globs: list[str]) -> bool:
    """O caminho relativo casa com algum dos padrões?

    A filtragem é feita sobre o que o WALKER emitiu, não varrendo o disco por
    conta própria. Isso não é só respeito ao teste arquitetural: significa que
    `--path` nunca alcança um arquivo que o walker não entregaria. Um
    `--path "*"` não passa a ler o `.env`, e `--path "../../etc/*"` não sai da
    raiz, porque o walker jamais emite esses caminhos.
    """
    from fnmatch import fnmatch

    alvo = rel_path.replace("\\", "/")
    for padrao in globs:
        p = padrao.replace("\\", "/")
        if fnmatch(alvo, p):
            return True
        # `src/**/*.py` precisa casar `src/a/b.py`; o fnmatch trata `*` como
        # qualquer coisa, inclusive `/`, então `**` já vem coberto — mas um
        # padrão sem diretório (`*.py`) deve casar o basename também, que é o
        # que a pessoa espera ao escrever `--path "*.py"`.
        if "/" not in p and fnmatch(alvo.rsplit("/", 1)[-1], p):
            return True
    return False
