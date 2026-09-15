"""Task Analyzer — decide executar agora ou documentar e decompor antes.

Determinístico e offline. O RAGX não tem um LLM e não vai ter (ADR-0015), então
a classificação vem de duas fontes, ambas auditáveis:

  1. sinais léxicos declarados em `signals.yaml`
  2. medição no ÍNDICE REAL — quantos módulos já falam do assunto, e se existe
     documento cobrindo

A segunda é o que separa isto de um casador de palavras: a mesma frase pontua
diferente num repositório onde o assunto aparece em cinco módulos e num onde
não aparece em lugar nenhum.

A limitação, dita de frente: ele lê palavras e mede impacto. Não entende o
pedido. Um pedido escrito de forma incomum pode ser subestimado — por isso
existe sobreposição, e ela fica registrada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ragx.config import Config
from ragx.tasks.models import Analysis, Classification, Scores

SIGNALS_PATH = Path(__file__).parent / "signals.yaml"

_DIMENSIONS = (
    "complexity", "architecture", "business_rule", "dependency", "risk",
    "security", "documentation",
)


@dataclass(frozen=True, slots=True)
class Signal:
    id: str
    dimension: str
    weight: int
    label: str
    reduce: bool
    #: `hard` marca o que NÃO pode ser anulado por um sinal de redução. Um typo
    #: continua sendo um typo, mas um typo dentro de código de criptografia
    #: merece uma olhada.
    hard: bool
    patterns: tuple[re.Pattern[str], ...]


@lru_cache(maxsize=1)
def load_signals() -> dict[str, Any]:
    data = yaml.safe_load(SIGNALS_PATH.read_text(encoding="utf-8"))
    sinais = [
        Signal(
            id=s["id"], dimension=s["dimension"], weight=int(s["weight"]),
            label=s.get("label", s["id"]), reduce=bool(s.get("reduce", False)),
            hard=bool(s.get("hard", False)),
            patterns=tuple(re.compile(p, re.IGNORECASE) for p in s["patterns"]),
        )
        for s in data["signals"]
    ]
    return {
        "signals": sinais,
        "gates": data.get("gates", {}),
        "bands": data.get("bands", []),
        "trivial": data.get("trivial", {}),
    }


def analyze(
    cfg: Config, request: str, measure: bool = True,
) -> Analysis:
    """Classifica a solicitação. Não escreve nada, em lugar nenhum."""
    texto = (request or "").strip()
    a = Analysis(request=texto)
    if not texto:
        a.reasoning_summary = "solicitação vazia"
        return a

    regras = load_signals()
    bruto: dict[str, int] = dict.fromkeys(_DIMENSIONS, 0)
    disparados: list[Signal] = []

    for s in regras["signals"]:
        if any(p.search(texto) for p in s.patterns):
            disparados.append(s)
            bruto[s.dimension] += s.weight

    # A trivialidade é decidida ANTES de medir. Não é só economia de I/O: medir
    # impacto de "mudar o texto do botão" faz a busca devolver doze resultados
    # vagamente parecidos, e o pedido passa a parecer que toca o sistema
    # inteiro. Pedido trivial não tem impacto para medir.
    trivial = _is_trivial(disparados, regras)

    if measure and not trivial:
        dep, doc, evidencias = _measure(cfg, texto)
        bruto["dependency"] += dep
        bruto["documentation"] += doc
        a.dependencies = evidencias
    elif not trivial:
        # Sem índice, presumir que falta documentação é mais seguro que
        # presumir que existe.
        bruto["documentation"] += 40

    scores = Scores(**{d: max(0, min(100, bruto[d])) for d in _DIMENSIONS})
    a.scores = scores
    a.matched = [s.id for s in disparados]

    total = 0 if trivial else scores.total
    # Redução que não chegou a tornar o pedido trivial ainda vale alguma coisa.
    # "Corrigir typo na mensagem do login" não é um projeto só porque a palavra
    # "login" apareceu — mas também não é um typo qualquer.
    if not trivial and any(s.reduce for s in disparados):
        total = round(total * 0.6)
    banda = _band(total, regras["bands"])

    # A estratégia sai da FAIXA; a classificação diz a NATUREZA da mudança.
    # São perguntas diferentes: "o que eu faço com isto" e "que tipo de coisa
    # isto é". Colapsar as duas jogaria fora ARCHITECTURAL_CHANGE,
    # SECURITY_CHANGE e companhia, que o pedido lista e que são o que um
    # revisor humano quer ver primeiro.
    a.requires_documentation = banda in (
        Classification.DOCUMENTATION_REQUIRED,
        Classification.TASK_DECOMPOSITION_REQUIRED,
    )
    a.requires_decomposition = banda is Classification.TASK_DECOMPOSITION_REQUIRED

    gates = regras["gates"]
    duro = [s for s in disparados if s.hard]
    seg_min = int(gates.get("security_never_direct", 40))

    # Porta que a média não atravessa: mudança de autenticação, dado pessoal ou
    # vulnerabilidade nunca é "faz agora". Um sinal de redução anula a
    # trivialidade do PEDIDO, não a gravidade do território.
    if (
        scores.security >= seg_min
        and banda is Classification.DIRECT_EXECUTION
        and (not trivial or any(s.dimension == "security" for s in duro))
    ):
        banda = Classification.ANALYSIS_REQUIRED
    if scores.security >= int(gates.get("security_needs_approval", 50)) and not trivial:
        a.requires_approval = True
    if scores.risk >= int(gates.get("risk_needs_approval", 60)):
        a.requires_approval = True

    # Território onde a faixa subestima: trocar o esquema de autenticação ou
    # apagar dado em produção cabe numa linha de pedido e leva semanas para
    # desfazer. O score é baixo porque o TEXTO é curto, não porque o trabalho é.
    #
    # Mas um pedido AMORTECIDO (typo que por acaso menciona login) só atravessa
    # esta porta se o sinal de segurança for `hard` — senão, corrigir a grafia
    # de uma mensagem de login viraria um projeto documentado, e a ferramenta
    # inteira perderia a confiança de quem a usa.
    amortecido = any(s.reduce for s in disparados)
    porta_seg = not amortecido or any(s.dimension == "security" for s in duro)
    porta_risco = not amortecido or any(s.dimension == "risk" for s in duro)
    if (
        not trivial and porta_seg
        and scores.security >= int(gates.get("security_needs_documentation", 60))
    ):
        a.requires_documentation = True
        banda = _at_least(banda, Classification.DOCUMENTATION_REQUIRED)
    if (
        not trivial and porta_risco
        and scores.risk >= int(gates.get("risk_needs_documentation", 70))
    ):
        a.requires_documentation = True
        banda = _at_least(banda, Classification.DOCUMENTATION_REQUIRED)

    # Decomposição é sobre AMPLITUDE de trabalho, não sobre um número alto.
    # Contar quantas preocupações distintas dispararam mede isso melhor que
    # calibrar a faixa até o caso de exemplo cair dentro dela.
    amplitude = sum(1 for d in _DIMENSIONS if scores.as_dict()[d] > 0)
    if a.requires_documentation and amplitude >= 4:
        a.requires_decomposition = True

    a.total = total
    a.classification = _nature(banda, scores, disparados, trivial)
    a.complexity = _complexity(total, scores)
    a.strategy = _strategy(a, banda)
    a.risks = [
        s.label for s in disparados
        if not s.reduce and s.dimension in ("risk", "security")
    ]
    a.confidence = _confidence(disparados, scores, trivial)
    a.reasoning_summary = _summary(disparados, scores, trivial, a)
    return a


_ESCALA = (
    Classification.DIRECT_EXECUTION,
    Classification.ANALYSIS_REQUIRED,
    Classification.DOCUMENTATION_REQUIRED,
    Classification.TASK_DECOMPOSITION_REQUIRED,
)


def _at_least(atual: Classification, minimo: Classification) -> Classification:
    ordem = {c: i for i, c in enumerate(_ESCALA)}
    return max(atual, minimo, key=lambda c: ordem.get(c, 0))


def _nature(
    banda: Classification, scores: Scores, disparados: list[Signal], trivial: bool,
) -> Classification:
    """Que TIPO de mudança é esta — independente do que fazer a respeito."""
    if trivial or banda is Classification.DIRECT_EXECUTION:
        return Classification.DIRECT_EXECUTION
    if not disparados:
        return Classification.UNKNOWN

    d = scores.as_dict()
    dominante = max(("security", "architecture", "business_rule"), key=lambda k: d[k])
    # Só vira rótulo específico quando a dimensão realmente domina; empate
    # técnico vira a classificação genérica da faixa, que é mais honesta.
    if d[dominante] >= 50 and d[dominante] >= max(d.values()) - 5:
        return {
            "security": Classification.SECURITY_CHANGE,
            "architecture": Classification.ARCHITECTURAL_CHANGE,
            "business_rule": Classification.PRODUCT_CHANGE,
        }[dominante]
    if any(s.id == "performance" for s in disparados) and d["complexity"] >= 30:
        return Classification.PERFORMANCE_CHANGE
    return banda


def override(
    a: Analysis, classification: str, by: str, reason: str,
) -> Analysis:
    """Sobreposição pelo agente. A justificativa fica registrada — sem ela, a
    sobreposição vira uma forma silenciosa de desligar o analisador."""
    if not reason.strip():
        raise ValueError("sobreposição exige justificativa")
    try:
        nova = Classification(classification)
    except ValueError as exc:
        validos = ", ".join(c.value for c in Classification)
        raise ValueError(f"classificação inválida; use uma de: {validos}") from exc
    a.classification = nova
    a.overridden_by = by
    a.override_reason = reason.strip()
    a.requires_documentation = nova in (
        Classification.DOCUMENTATION_REQUIRED,
        Classification.TASK_DECOMPOSITION_REQUIRED,
    )
    a.requires_decomposition = nova is Classification.TASK_DECOMPOSITION_REQUIRED
    a.strategy = _strategy(a, nova)
    a.reasoning_summary = f"sobreposto por {by}: {reason.strip()[:200]}"
    return a


# ── medição no índice ───────────────────────────────────────────────────
def _measure(cfg: Config, texto: str) -> tuple[int, int, list[str]]:
    """Quanto do repositório o assunto já toca, e se já existe documento.

    Falha de índice não derruba a análise: sem banco, devolve neutro e a
    classificação sai só dos sinais léxicos. Um analisador que exige índice
    pronto seria inútil no primeiro uso.
    """
    try:
        from ragx.search.service import search
    except Exception:
        return 0, 40, []
    if not cfg.db_path.exists():
        return 0, 40, []

    try:
        out = search(cfg, texto, mode="hybrid", limit=12)
    except Exception:
        return 0, 40, []

    # Só conta o que casou por PALAVRA-CHAVE. Resultado apenas semântico para
    # uma frase genérica é ruído: a busca sempre devolve alguma coisa, e sem
    # este filtro todo pedido parece tocar o repositório inteiro.
    relevantes = [r for r in out.results if "keyword" in getattr(r, "matched_by", ())]
    if not relevantes:
        # Assunto que o repositório não conhece: nada a quebrar, mas nada
        # documentado também.
        return 0, 60, []

    caminhos = [r.document_path for r in relevantes]
    modulos = {_module_of(p) for p in caminhos}
    codigo = [p for p in caminhos if not _is_doc(p)]
    docs = [p for p in caminhos if _is_doc(p) and not p.startswith("@base/")]

    # Mais módulos tocados = mais chance de efeito colateral.
    dep = min(100, len(modulos) * 12 + len(codigo) * 3)
    # Documento existente derruba a necessidade de documentar.
    doc = 60 if not docs else max(0, 40 - len(docs) * 12)

    evidencias = []
    for p in caminhos:
        if p not in evidencias:
            evidencias.append(p)
        if len(evidencias) >= 6:
            break
    return dep, doc, evidencias


def _module_of(rel_path: str) -> str:
    partes = rel_path.replace("\\", "/").split("/")
    return "/".join(partes[:2]) if len(partes) > 1 else partes[0]


def _is_doc(rel_path: str) -> bool:
    return rel_path.lower().endswith((".md", ".rst", ".txt", ".adoc"))


# ── decisão ─────────────────────────────────────────────────────────────
def _is_trivial(disparados: list[Signal], regras: dict[str, Any]) -> bool:
    """Um typo continua sendo um typo mesmo contendo a palavra 'login'.

    Metade do valor do analisador está aqui: se ele transformasse tudo em
    projeto, ninguém o usaria — e a burocracia extra é o que faz as pessoas
    desligarem a ferramenta.

    A regra é comparativa, não absoluta: a redução vence quando é declarada
    mais forte que o maior sinal de aumento. "Corrigir typo" (-60) supera
    "toca autenticação" (65)? Não — e é por isso que esse caso vai para
    ANALYSIS_REQUIRED, não para DIRECT_EXECUTION.
    """
    reducoes = [s for s in disparados if s.reduce]
    if not reducoes:
        return False
    aumentos = [s for s in disparados if not s.reduce]
    if not aumentos:
        return True
    forte = int(regras["trivial"].get("strong_weight", 40))
    maior_aumento = max(s.weight for s in aumentos)
    maior_reducao = max(-s.weight for s in reducoes)
    if maior_aumento < forte:
        return True
    return maior_reducao >= maior_aumento


def _band(total: int, bands: list[dict[str, Any]]) -> Classification:
    for b in bands:
        if total <= int(b["max"]):
            return Classification(b["classification"])
    return Classification.TASK_DECOMPOSITION_REQUIRED


def _complexity(total: int, scores: Scores) -> str:
    if total >= 76 or scores.risk >= 60:
        return "critical" if scores.risk >= 60 and total >= 70 else "high"
    if total >= 51:
        return "high"
    if total >= 26:
        return "medium"
    return "low"


def _strategy(a: Analysis, banda: Classification) -> str:
    if a.requires_decomposition:
        return "DOCUMENT -> DECOMPOSE -> EXECUTE"
    if a.requires_documentation:
        return "DOCUMENT -> EXECUTE"
    if banda is Classification.ANALYSIS_REQUIRED:
        return "ANALYZE -> EXECUTE"
    return "EXECUTE"


def _confidence(disparados: list[Signal], scores: Scores, trivial: bool) -> float:
    """Confiança é sobre o SINAL, não sobre o acerto.

    Nenhum sinal disparado = quase nenhuma base. Muitos sinais concordando =
    base razoável. Isto não promete que a classificação está certa; promete
    dizer quando ela está apoiada em pouca coisa.
    """
    if not disparados:
        return 0.25
    positivos = [s for s in disparados if not s.reduce]
    if trivial:
        return 0.85
    base = 0.45 + min(0.35, len(positivos) * 0.07)
    if scores.total >= 70 or scores.total <= 15:
        base += 0.08  # extremos são mais fáceis de acertar que o meio
    return round(min(0.95, base), 2)


def _summary(
    disparados: list[Signal], scores: Scores, trivial: bool, a: Analysis,
) -> str:
    """Justificativa curta e operacional. Não é raciocínio de modelo."""
    if trivial:
        motivos = [s.label for s in disparados if s.reduce]
        return f"Pedido pontual ({'; '.join(motivos[:2])}); não justifica documentação."
    if not disparados:
        return "Nenhum sinal reconhecido; classificado pelo impacto medido no índice."

    partes = [s.label for s in disparados if not s.reduce][:3]
    if a.dependencies:
        partes.append(f"{len(a.dependencies)} arquivo(s) existentes tocam o assunto")
    if scores.documentation >= 50:
        partes.append("nenhum documento cobre o assunto")
    return " · ".join(partes) + "."
