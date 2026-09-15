from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import BudgetExceededError
from ragx.sizing.budget import Budget

pytestmark = pytest.mark.unit


@pytest.fixture
def cfg(tmp_path: Path):
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    return load_config(tmp_path)


def test_projecao_bate_com_a_ordem_de_grandeza_documentada(cfg) -> None:
    """100k chunks com int8@256 deve caber abaixo de 50 MB (docs/16)."""
    b = Budget(cfg)
    assert b.project(100_000, 256) < 50 * 1024 * 1024


def test_versionar_float32_estouraria(cfg) -> None:
    b = Budget(cfg)
    assert b.project(100_000, 3072) > cfg.size.fail_total_bytes


def test_enforce_recusa_em_vez_de_truncar(cfg) -> None:
    b = Budget(cfg)
    with pytest.raises(BudgetExceededError, match="Nada foi gravado"):
        b.enforce(100_000, 3072)


def test_enforce_passa_dentro_do_orcamento(cfg) -> None:
    Budget(cfg).enforce(50_000, 256)


def test_max_chunks_e_respeitado(cfg) -> None:
    with pytest.raises(BudgetExceededError, match="max_chunks"):
        Budget(cfg).enforce(cfg.size.max_chunks + 1, 256)


def test_report_em_projeto_vazio(cfg) -> None:
    r = Budget(cfg).report()
    assert r["bytes"] == 0 and not r["exceeded"] and r["oversized"] == []


def test_sugestoes_sao_acionaveis(cfg) -> None:
    b = Budget(cfg)
    with pytest.raises(BudgetExceededError) as exc:
        b.enforce(100_000, 3072, contributors={"vendor/bundles/**": 90_000})
    msg = str(exc.value)
    assert "vendor/bundles" in msg and "versioned_dim" in msg and ".ragignore" in msg
