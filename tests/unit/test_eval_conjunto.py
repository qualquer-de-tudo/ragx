"""O conjunto de avaliação (RAGX-0099): o instrumento não pode encolher nem apodrecer.

Sem estes testes, apagar consultas ou mudar um arquivo de lugar tornava o `ragx eval` silenciosamente
inconclusivo: com n=26 o IC95% do recall@5 tem ~0,33 de largura e nenhuma mudança de recuperação é falsificável.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from ragx.search import evaluation
from ragx.search.evaluation import (
    CLASSES,
    DIFFICULTIES,
    MAX_CI_WIDTH,
    EvalCase,
    load_cases,
    wilson_ci,
)

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[2]
CASOS = load_cases(RAIZ / "tests" / "eval" / "queries.yaml")
RESPONDIDAS = [c for c in CASOS if not c.no_answer]


def test_o_conjunto_tem_pelo_menos_150_consultas_e_nao_repete() -> None:
    assert len(CASOS) >= 150, f"o conjunto encolheu para {len(CASOS)}"
    repetidas = [q for q, n in Counter(c.query for c in CASOS).items() if n > 1]
    assert not repetidas, repetidas


def test_a_largura_do_ic_no_pior_caso_fica_abaixo_do_limite() -> None:
    """No PIOR caso (recall 0,5) o IC95% do recall@5 com as consultas respondidas cabe em 0,20 (o CI falha se encolher)."""
    n = len(RESPONDIDAS)
    baixo, alto = wilson_ci(n // 2, n)
    assert alto - baixo <= MAX_CI_WIDTH, f"n={n} respondidas: largura {alto - baixo:.3f} > {MAX_CI_WIDTH}"


def test_cada_classe_tem_cobertura_suficiente() -> None:
    por_classe = Counter(c.cls for c in CASOS)
    assert set(por_classe) <= set(CLASSES), set(por_classe) - set(CLASSES)
    for classe in ("relacionamento", "depuracao", "arquitetura", "configuracao", "sem_resposta"):
        assert por_classe[classe] >= 15, f"classe {classe} com {por_classe[classe]} consultas"
    assert por_classe["factual"] >= 30


def test_dificuldade_valida_e_as_duas_existem() -> None:
    por_dif = Counter(c.difficulty for c in CASOS)
    assert set(por_dif) <= set(DIFFICULTIES)
    assert por_dif["easy"] >= 20 and por_dif["hard"] >= 20


def test_todo_caso_diz_por_que_aqueles_caminhos_sao_os_relevantes() -> None:
    sem_nota = [c.query for c in CASOS if len(c.note.strip()) < 8]
    assert not sem_nota, sem_nota


def test_todo_caminho_relevante_existe_e_consulta_sem_resposta_nao_tem_caminho() -> None:
    inexistentes = [(c.query, p) for c in RESPONDIDAS for p in c.relevant_paths if not (RAIZ / p).exists()]
    assert not inexistentes, f"relevant_paths apontam para arquivo que não existe mais: {inexistentes}"
    assert all(c.relevant_paths for c in RESPONDIDAS), [c.query for c in RESPONDIDAS if not c.relevant_paths]
    assert all(not c.relevant_paths for c in CASOS if c.no_answer)


def test_consulta_sem_resposta_nao_conta_como_falha_de_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    """`sem_resposta` fica fora do recall/MRR/nDCG e tem a própria métrica (falso positivo)."""
    casos = [
        EvalCase("a", ("x.py",), cls="factual", difficulty="easy"),
        EvalCase("b", ("y.py",), cls="arquitetura", difficulty="hard"),
        EvalCase("c", (), cls="sem_resposta"),
        EvalCase("d", (), cls="sem_resposta"),
    ]
    # `a` acerta com score 0,9; `b` erra; `c` volta algo com score 0,95 (falso positivo); `d` volta algo fraco
    respostas = {
        "a": [("x.py", 0.9)],
        "b": [("z.py", 0.5)],
        "c": [("w.py", 0.95)],
        "d": [("w.py", 0.1)],
    }

    def falso(cfg, q, mode, limit):  # type: ignore[no-untyped-def]
        return SimpleNamespace(results=[SimpleNamespace(document_path=p, score=s) for p, s in respostas[q]])

    monkeypatch.setattr(evaluation, "search", falso)
    (m,) = evaluation.evaluate(object(), casos, ("keyword",))  # type: ignore[arg-type]
    assert m.cases == 2 and m.recall_at_5 == 0.5  # só as respondidas
    assert m.by_class == {"factual": (1, 1), "arquitetura": (0, 1)}
    assert m.by_difficulty == {"easy": (1, 1), "hard": (0, 1)}
    assert m.no_answer_cases == 2 and m.no_answer_false_positives == 1
    assert m.no_answer_threshold == 0.9 and m.no_answer_fp_rate == 0.5


def test_o_carregador_aceita_o_formato_antigo_sem_class_nem_difficulty(tmp_path: Path) -> None:
    arq = tmp_path / "q.yaml"
    arq.write_text('- query: "x"\n  relevant_paths: ["a.py"]\n', encoding="utf-8")
    (c,) = load_cases(arq)
    assert c.cls == "factual" and c.difficulty == "easy" and not c.no_answer
