"""Escrita que só toca o arquivo quando o conteúdo mudou (RAGX-0148)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ragx.sync.stable_write import write_bytes_if_changed, write_text_if_changed

pytestmark = pytest.mark.unit


def _antigo(p: Path) -> int:
    os.utime(p, ns=(1_000_000_000, 1_000_000_000))
    return p.stat().st_mtime_ns


def test_conteudo_igual_nao_toca_o_arquivo(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    assert write_text_if_changed(p, '{"a": 1}\n') is True
    mt = _antigo(p)
    assert write_text_if_changed(p, '{"a": 1}\n') is False
    assert p.stat().st_mtime_ns == mt


def test_conteudo_diferente_grava_e_cria_a_pasta(tmp_path: Path) -> None:
    p = tmp_path / "x" / "y" / "a.json"
    assert write_text_if_changed(p, "um\n") is True
    assert write_text_if_changed(p, "dois\n") is True
    assert p.read_text(encoding="utf-8") == "dois\n"


def test_chave_volatil_ignorada_em_qualquer_nivel(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    velho = {"generated_at": "2026-01-01", "project": {"generated_at": "2026-01-01", "n": 1}, "itens": [{"generated_at": "x", "k": 1}]}
    novo = {"generated_at": "2026-02-02", "project": {"generated_at": "2026-02-02", "n": 1}, "itens": [{"generated_at": "y", "k": 1}]}
    write_text_if_changed(p, json.dumps(velho), volatile=("generated_at",))
    mt = _antigo(p)
    assert write_text_if_changed(p, json.dumps(novo), volatile=("generated_at",)) is False
    assert p.stat().st_mtime_ns == mt and "2026-01-01" in p.read_text(encoding="utf-8")


def test_mudanca_de_conteudo_grava_com_o_generated_at_novo(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    write_text_if_changed(p, json.dumps({"generated_at": "A", "n": 1}), volatile=("generated_at",))
    assert write_text_if_changed(p, json.dumps({"generated_at": "B", "n": 2}), volatile=("generated_at",)) is True
    assert json.loads(p.read_text(encoding="utf-8")) == {"generated_at": "B", "n": 2}


def test_json_existente_invalido_e_regravado(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    p.write_text("{isso nao e json", encoding="utf-8")
    assert write_text_if_changed(p, '{"a": 1}\n', volatile=("generated_at",)) is True
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}


def test_bytes_iguais_nao_tocam_e_diferentes_gravam(tmp_path: Path) -> None:
    p = tmp_path / "s.i8"
    assert write_bytes_if_changed(p, b"\x00\x01\x02") is True
    mt = _antigo(p)
    assert write_bytes_if_changed(p, b"\x00\x01\x02") is False and p.stat().st_mtime_ns == mt
    assert write_bytes_if_changed(p, b"\x00\x01\x03") is True


def test_lf_sem_bom_e_sem_traducao(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    write_text_if_changed(p, "a\nb\n")
    assert p.read_bytes() == b"a\nb\n"
