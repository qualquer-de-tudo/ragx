"""`dump`, `compact` e `cap` (RAGX-0155)."""

from __future__ import annotations

import pytest

from ragx.mcp.tools import cap, compact, dump

pytestmark = pytest.mark.unit


def test_dump_e_compacto_e_preserva_acentos() -> None:
    assert dump({"a": [1, 2], "b": "ação"}) == '{"a":[1,2],"b":"ação"}'


def test_compact_remove_chaves_nulas_inclusive_em_dicts_dentro_de_listas() -> None:
    entrada = {"a": None, "b": 0, "c": "", "d": [{"x": None, "y": 1}, None], "e": {"z": None}}
    assert compact(entrada) == {"b": 0, "c": "", "d": [{"y": 1}, None], "e": {}}


def test_compact_nao_mexe_em_falsos_que_nao_sao_nulos() -> None:
    assert compact({"a": False, "b": 0, "c": [], "d": ""}) == {"a": False, "b": 0, "c": [], "d": ""}


def test_cap_mede_o_texto_compacto() -> None:
    carga = {"ok": True, "data": {"x": "a" * 100}}
    tamanho = len(dump(carga).encode("utf-8"))
    assert cap(carga, max_bytes=tamanho) == carga  # cabe exatamente no compacto
    assert cap(carga, max_bytes=tamanho - 1)["error"]["code"] == "too_large"
