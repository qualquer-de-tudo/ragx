"""Os Benchmarks públicos: a página `docs/27-benchmarks.md` é gerada do JSON do painel e nunca diverge dele."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[2]


def _gerador():
    spec = importlib.util.spec_from_file_location("gerar_benchmarks", RAIZ / "scripts" / "gerar_benchmarks.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gerar_benchmarks"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_a_pagina_publica_bate_com_o_json_do_painel() -> None:
    g = _gerador()
    esperado = g.gerar(json.loads(g.JSON.read_text(encoding="utf-8")))
    assert g.DOC.read_text(encoding="utf-8") == esperado, "rode `uv run python scripts/gerar_benchmarks.py`"


def test_formatacao_em_portugues() -> None:
    g = _gerador()
    assert g.num(7684) == "7.684"
    assert g.num(1.77) == "1,77"
    assert g.num(40.0) == "40"
    assert g.num(0.05) == "0,05"
    assert g.pct(-61.5) == "−62%"
    assert g.pct(-0.8) == "−0,8%"
    assert g.pct(None) == "—"
    assert g.data("2026-10-02") == "2 de out de 2026"
    assert g.r2(0.6) == "0,60"


def test_meta_nao_atingida_e_resultado_inconclusivo_aparecem_na_pagina() -> None:
    texto = (RAIZ / "docs" / "27-benchmarks.md").read_text(encoding="utf-8")
    assert "**não atingida**" in texto
    assert "Inconclusivo em tokens faturáveis" in texto
    assert "melhor extremo" in texto


def test_metas_do_json_sao_coerentes_com_o_ultimo_valor() -> None:
    dados = json.loads(_gerador().JSON.read_text(encoding="utf-8"))
    for m in dados["metrics"]:
        if not m.get("goal"):
            continue
        agora = m["points"][-1]["value"]
        ok = agora <= m["goal"]["value"] if m["lowerIsBetter"] else agora >= m["goal"]["value"]
        assert ok == m["goal"]["met"], f"{m['id']}: {agora} contra a meta {m['goal']['value']}"
