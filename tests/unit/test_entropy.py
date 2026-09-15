from __future__ import annotations

import pytest

from ragx.security.entropy import looks_random, shannon

pytestmark = pytest.mark.unit


def test_entropia_de_texto_natural_e_baixa() -> None:
    assert shannon("the quick brown fox jumps") < 4.2


def test_entropia_de_chave_aleatoria_e_alta() -> None:
    assert shannon("hQ7vN2mK9pL4xR8tW3zA6bY1cD5eF0gJ") > 4.0


def test_string_vazia_nao_quebra() -> None:
    assert shannon("") == 0.0


@pytest.mark.parametrize("value", ["aaaaaaaaaaaaaaaa", "1111111111111111", "short"])
def test_repeticao_e_curto_nao_sao_aleatorios(value: str) -> None:
    assert not looks_random(value)


def test_frase_com_espacos_nao_e_segredo() -> None:
    assert not looks_random("esta e uma frase normal de documentacao")


def test_chave_real_e_detectada() -> None:
    assert looks_random("hQ7vN2mK9pL4xR8tW3zA6bY1cD5eF0gJ")
