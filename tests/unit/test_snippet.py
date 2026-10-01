"""`make_snippet`: o trecho curto que a busca `concise` devolve no lugar do conteúdo."""

from __future__ import annotations

import pytest

from ragx.search.snippet import make_snippet

pytestmark = pytest.mark.unit


def test_conteudo_menor_que_o_limite_volta_inteiro_e_sem_reticencias() -> None:
    assert make_snippet("def f():\n    return 1\n", 200) == "def f():\n    return 1"


def test_corta_em_fim_de_linha_quando_ha_uma_perto() -> None:
    texto = "linha um bem comprida\nlinha dois bem comprida\nlinha tres bem comprida\n"
    s = make_snippet(texto, 50)
    assert s.endswith("…") and "\n" not in s.rstrip("…")[-3:]
    assert s.rstrip("…") in texto and len(s) <= 51
    assert s.rstrip("…").endswith("comprida")  # terminou numa linha inteira


def test_sem_quebra_de_linha_corta_em_limite_de_palavra() -> None:
    s = make_snippet("uma frase muito longa " * 20, 40)
    corpo = s.removesuffix("…")
    assert len(corpo) <= 40 and not corpo.endswith(" ") and corpo.rsplit(" ", 1)[-1] in ("longa", "muito", "frase", "uma")
    assert s.endswith("…")


def test_acentos_e_emoji_nao_sao_partidos() -> None:
    texto = "ação 😀 " * 40
    for limite in range(5, 40):
        s = make_snippet(texto, limite)
        s.encode("utf-8")  # não pode levantar (surrogate solto)
        assert s.removesuffix("…") == s.removesuffix("…").rstrip()


def test_palavra_unica_maior_que_o_limite_corta_no_limite() -> None:
    s = make_snippet("a" * 500, 20)
    assert s == "a" * 20 + "…"


def test_limite_invalido_nao_quebra() -> None:
    assert make_snippet("abc", 0) == "…" or make_snippet("abc", 0) == ""
