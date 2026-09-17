"""Camada do documento: conhecimento, registro de trabalho ou teste.

Um repositório não guarda só conhecimento. Guarda também o REGISTRO de como o
conhecimento foi construído — tarefas, backlog, rascunhos de ADR — e os testes.
Os três falam do mesmo assunto, com o mesmo vocabulário, e disputam as mesmas
vagas do top-K.

Medido neste repositório: `task/` é **22% dos chunks** (543 contra 321 de
`docs/`). Para a consulta *"como o security gate decide bloquear um arquivo"*,
o primeiro fragmento devolvido era o enunciado da TAREFA que pediu para
construir o gate — não o `admit()` que o implementa. Documento de planejamento
é quase-duplicata semântica da documentação: mesmo assunto, mesmas palavras,
menos informação.

A correção não é excluir: às vezes a resposta está mesmo na tarefa, e um
`task/` invisível seria pior que um `task/` ruidoso. É **pesar**.

## Por que a classificação acontece na LEITURA

A alternativa seria uma coluna `tier` em `documents`, gravada na indexação.
Ela seria mais rápida por uma margem que não importa (uma comparação de
caminho por resultado) e teria um defeito real: mudar `work_paths` no
`ragx.toml` só surtiria efeito depois de reindexar o projeto inteiro. Como a
classificação é uma POLÍTICA — e política se ajusta —, ela mora onde pode
mudar sem custo.

Ver `task/fase-14-evolucao-do-rag/RAGX-0102-*.md`.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pathspec import GitIgnoreSpec


class Tier(StrEnum):
    #: O que o projeto SABE: código, documentação, conhecimento base.
    KNOWLEDGE = "knowledge"
    #: Como o projeto foi construído: tarefas, backlog, planos, rascunhos.
    WORK = "work"
    #: Testes. Respondem "como isto é verificado", raramente "como isto funciona".
    TEST = "test"


#: Defaults que funcionam sem configuração nenhuma. Deliberadamente curtos: um
#: default que classifica demais silenciosamente esconde conhecimento legítimo.
DEFAULT_WORK = (
    "task/",
    "tasks/",
    "backlog/",
    "stories/",
    "planning/",
)
DEFAULT_TEST = (
    "tests/",
    "test/",
    "spec/",
    "specs/",
    "__tests__/",
)


@lru_cache(maxsize=32)
def _spec(padroes: tuple[str, ...]) -> GitIgnoreSpec:
    """Mesma sintaxe do `.gitignore`, que é a que todo mundo já conhece."""
    return GitIgnoreSpec.from_lines(padroes)


def classify(
    rel_path: str,
    work: tuple[str, ...] = DEFAULT_WORK,
    test: tuple[str, ...] = DEFAULT_TEST,
) -> Tier:
    """A camada de um caminho relativo.

    `work` vence `test` quando os dois casam: um `task/tests-do-plano.md` é
    plano, não teste.
    """
    p = rel_path.replace("\\", "/").lstrip("./")
    if work and _spec(work).match_file(p):
        return Tier.WORK
    if test and _spec(test).match_file(p):
        return Tier.TEST
    return Tier.KNOWLEDGE


def weight_for(tier: Tier, work_weight: float, test_weight: float) -> float:
    """Multiplicador de ranking da camada. `knowledge` é sempre 1,0 — ele é a
    referência, e mexer nele deslocaria a escala inteira sem mudar a ordem."""
    if tier is Tier.WORK:
        return work_weight
    if tier is Tier.TEST:
        return test_weight
    return 1.0
