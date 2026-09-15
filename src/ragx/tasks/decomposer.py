"""Task Decomposer — do plano para tarefas executáveis, com dependências.

Duas regras governam este módulo:

  1. **Toda tarefa nasce com critério de aceite.** Sem isso, `completed` não
     significa nada e a validação não tem o que verificar. O repositório
     recusa a tarefa sem critério; aqui ela nunca é criada assim.

  2. **O grafo é acíclico por construção.** O ciclo é recusado na criação da
     aresta, com o caminho completo na mensagem — descobrir na execução
     significa descobrir com o board já montado e a fila travada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ragx.config import Config
from ragx.tasks.models import Analysis, DependencyKind, Status, Task
from ragx.tasks.planner import DocPlan
from ragx.tasks.store import TaskRepository


@dataclass
class Track:
    """Uma trilha de trabalho: o que ela entrega e do que depende."""

    id: str
    title: str
    type: str
    depends_on_tracks: tuple[str, ...] = ()
    priority: str = "medium"
    acceptance: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    security: tuple[str, ...] = ()
    performance: tuple[str, ...] = ()
    #: Dimensão do analisador que justifica a trilha. Sem sinal, sem trilha —
    #: é o que impede o decompositor de criar 11 tarefas para todo pedido.
    requires_score: str | None = None
    min_score: int = 40


#: Ordem é a ordem natural de execução; o DAG real sai de `depends_on_tracks`.
TRACKS: tuple[Track, ...] = (
    Track(
        "analysis", "Analisar o estado atual", "analysis",
        priority="high",
        acceptance=(
            "Módulos, entidades e contratos afetados listados com caminho",
            "Restrições e decisões já existentes identificadas",
            "Lacunas de conhecimento registradas como pendência",
        ),
    ),
    Track(
        "documentation", "Escrever a documentação planejada", "documentation",
        depends_on_tracks=("analysis",), priority="high",
        acceptance=(
            "Toda seção marcada como pendente foi escrita ou explicitamente adiada",
            "Cada afirmação aponta para código ou documento existente",
            "Nenhum segredo, URL interna ou dado real no texto",
        ),
    ),
    Track(
        "database", "Modelar e migrar o banco", "database",
        depends_on_tracks=("documentation",), priority="high",
        requires_score="architecture", min_score=45,
        acceptance=(
            "Migração aplica e reverte em ambiente limpo",
            "Índices justificados para as consultas previstas",
            "Dado existente continua íntegro após a migração",
        ),
        tests=("migração aplicada e revertida em banco de teste",),
        security=("nenhum dado pessoal novo sem base legal registrada",),
    ),
    Track(
        "backend", "Implementar o backend", "technical",
        depends_on_tracks=("documentation", "database"), priority="high",
        acceptance=(
            "Regra de negócio isolada da camada de entrada",
            "Toda entrada validada na borda",
            "Erro esperado tem tipo próprio",
        ),
        tests=("unitário para a regra de negócio", "integração para cada endpoint"),
        security=("autorização verificada no servidor, por recurso",),
    ),
    Track(
        "integration", "Implementar a integração", "integration",
        depends_on_tracks=("backend",),
        requires_score="architecture", min_score=50,
        acceptance=(
            "Cliente externo atrás de interface do projeto",
            "Timeout, retry com backoff e limite configurados",
            "Operação idempotente sob repetição",
        ),
        tests=("contrato do parceiro com dublê",),
    ),
    Track(
        "frontend", "Implementar a interface", "technical",
        depends_on_tracks=("backend",),
        requires_score="business_rule", min_score=50,
        acceptance=(
            "Estado de carregamento, vazio e erro tratados",
            "Nenhuma regra de negócio duplicada no cliente",
        ),
        tests=("teste de componente para o fluxo principal",),
    ),
    Track(
        "tests", "Cobrir com testes", "testing",
        depends_on_tracks=("backend",), priority="high",
        acceptance=(
            "Caminho feliz, erro de validação e negação de acesso cobertos",
            "Casos de borda: vazio, limite exato, limite mais um",
            "Cobertura do código novo não caiu",
        ),
        tests=("suíte completa verde",),
    ),
    Track(
        "security", "Revisão de segurança", "security",
        depends_on_tracks=("backend", "tests"), priority="high",
        requires_score="security", min_score=40,
        acceptance=(
            "Superfície nova revisada contra a lista de verificação",
            "Nenhum segredo no código, no log ou na resposta",
            "Achado não corrigido virou débito com severidade e prazo",
        ),
        security=("revisão obrigatória antes de considerar concluído",),
    ),
    Track(
        "performance", "Revisão de performance", "performance",
        depends_on_tracks=("backend", "tests"),
        requires_score="complexity", min_score=60,
        acceptance=(
            "Medição antes e depois, com número",
            "Nenhuma consulta por item em laço",
            "Listagem paginada com teto",
        ),
        performance=("medir antes de otimizar; reportar o número real",),
    ),
    Track(
        "deploy", "Preparar a implantação", "deployment",
        depends_on_tracks=("tests",),
        requires_score="risk", min_score=50,
        acceptance=(
            "Passos de implantação escritos e testados em staging",
            "Rollback testado, não apenas descrito",
        ),
    ),
    Track(
        "observability", "Instrumentar", "operations",
        depends_on_tracks=("backend",),
        requires_score="risk", min_score=50,
        acceptance=(
            "Caminho crítico emite log estruturado com correlação",
            "Nenhum dado sensível no log",
            "Métrica de erro e latência por endpoint novo",
        ),
    ),
    Track(
        "validation", "Validar a entrega", "validation",
        depends_on_tracks=("tests",), priority="high",
        acceptance=(
            "Todo critério de aceite das tarefas anteriores conferido",
            "Conhecimento novo promovido para a base",
            "Débitos e riscos remanescentes registrados",
        ),
    ),
)


@dataclass
class Decomposition:
    project_id: str = ""
    tasks: list[Task] = field(default_factory=list)
    edges: list[tuple[str, str, DependencyKind]] = field(default_factory=list)
    skipped_tracks: list[str] = field(default_factory=list)


def decompose(
    cfg: Config, analysis: Analysis, docplan: DocPlan, project_id: str,
    repo: TaskRepository | None = None,
) -> Decomposition:
    """Monta as tarefas. Só persiste se `repo` for passado."""
    scores = analysis.scores.as_dict()
    d = Decomposition(project_id=project_id)

    ativas: dict[str, str] = {}  # track_id -> task_id
    seq = 0
    escopo = _scope(analysis, docplan)

    for track in TRACKS:
        if track.requires_score and scores.get(track.requires_score, 0) < track.min_score:
            d.skipped_tracks.append(track.id)
            continue
        if track.id == "documentation" and not docplan.docs:
            d.skipped_tracks.append(track.id)
            continue

        seq += 1
        task_id = f"{project_id}-T{seq:03d}"
        aceite = list(track.acceptance)
        descricao = _describe(track, analysis, docplan)

        if track.id == "documentation":
            aceite = [
                f"`{doc.rel_path}` escrito, sem seção pendente" for doc in docplan.docs
            ] + aceite

        d.tasks.append(
            Task(
                id=task_id, project_id=project_id, seq=seq,
                title=track.title, description=descricao, type=track.type,
                track=track.id, status=Status.PENDING,
                priority=_priority(track, analysis),
                complexity=analysis.complexity,
                acceptance_criteria=aceite,
                required_context=list(analysis.dependencies[:5]),
                required_skills=[track.type],
                files_scope=escopo,
                security_requirements=list(track.security),
                performance_requirements=list(track.performance),
                test_requirements=list(track.tests),
                requires_approval=analysis.requires_approval
                and track.id in ("database", "deploy", "security"),
            )
        )
        ativas[track.id] = task_id

    for track in TRACKS:
        atual = ativas.get(track.id)
        if not atual:
            continue
        for dep_track in track.depends_on_tracks:
            anterior = ativas.get(dep_track)
            if anterior:
                d.edges.append((atual, anterior, DependencyKind.DEPENDS_ON))

    if repo is not None:
        for t in d.tasks:
            repo.create_task(t)
        for task_id, depends_on, kind in d.edges:
            repo.add_dependency(task_id, depends_on, kind)
        # A primeira tarefa não depende de ninguém: já nasce executável, senão o
        # board é criado inteiro em `pending` e o worker precisa de um ciclo só
        # para descobrir isso.
        repo.promote_ready(project_id)
    return d


def _priority(track: Track, analysis: Analysis) -> str:
    if analysis.requires_approval and track.id in ("security", "database"):
        return "critical"
    return track.priority


def _describe(track: Track, analysis: Analysis, docplan: DocPlan) -> str:
    linhas = [f"Solicitação original: {analysis.request}", ""]
    if track.id == "analysis" and docplan.context_sources:
        linhas += ["Comece pelo que já existe:"]
        linhas += [f"  - {s}" for s in docplan.context_sources[:6]]
    elif track.id == "documentation":
        linhas += ["Documentos planejados:"]
        linhas += [f"  - {d.doc_type}: {d.rel_path}" for d in docplan.docs]
        pendencias = [g for d in docplan.docs for g in d.gaps]
        if pendencias:
            linhas += ["", "Lacunas identificadas pelo planner:"]
            linhas += [f"  - {g}" for g in pendencias[:5]]
    elif docplan.entities:
        linhas += ["Entidades relacionadas no grafo:"]
        linhas += [f"  - {e}" for e in docplan.entities[:8]]
    return "\n".join(linhas)


def _scope(analysis: Analysis, docplan: DocPlan) -> list[str]:
    """Arquivos que a tarefa provavelmente toca, derivados do índice.

    É o que o validador usa depois para recusar resultado que mexeu onde não
    devia. Prefixo de diretório, não arquivo exato: o escopo precisa permitir
    criar arquivo novo no lugar certo.
    """
    escopo: list[str] = []
    for caminho in analysis.dependencies + docplan.context_sources:
        if caminho.startswith("@base/"):
            continue
        partes = caminho.replace("\\", "/").split("/")
        prefixo = "/".join(partes[:2]) if len(partes) > 2 else caminho
        if prefixo not in escopo:
            escopo.append(prefixo)
    for doc in docplan.docs:
        pasta = doc.rel_path.rsplit("/", 1)[0]
        if pasta not in escopo:
            escopo.append(pasta)
    return escopo[:12]


def project_id_for(request: str) -> str:
    """ID curto, estável e legível a partir da solicitação."""
    import hashlib

    termos = re.findall(r"[a-z0-9]{3,}", (request or "").lower())[:3]
    base = "-".join(termos) or "proj"
    h = hashlib.sha256((request or "").encode("utf-8")).hexdigest()[:6]
    return f"{base[:24]}-{h}"
