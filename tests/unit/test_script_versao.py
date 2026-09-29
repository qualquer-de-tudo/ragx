"""`scripts/versao.py`: a versão sobe junto em todo lugar, e o CHANGELOG fecha a seção."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ARQ = Path(__file__).resolve().parents[2] / "scripts" / "versao.py"
_spec = importlib.util.spec_from_file_location("versao", _ARQ)
assert _spec and _spec.loader
versao = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(versao)

CL = """# Changelog

## [Não lançado]

### Adicionado

- coisa nova

## [1.0.0-beta.3] — 2026-09-17

- velha
"""


def test_changelog_abre_a_secao_da_versao_e_deixa_nao_lancado_vazio() -> None:
    novo = versao.changelog(CL, "1.0.0-beta.4", date(2026, 9, 29))
    assert novo == (
        "# Changelog\n\n## [Não lançado]\n\n## [1.0.0-beta.4] — 2026-09-29\n\n"
        "### Adicionado\n\n- coisa nova\n\n## [1.0.0-beta.3] — 2026-09-17\n\n- velha\n"
    )


def test_changelog_recusa_secao_vazia_e_versao_repetida() -> None:
    vazio = "## [Não lançado]\n\n### Adicionado\n\n## [1.0.0] — 2026-01-01\n\n- x\n"
    with pytest.raises(versao.RecusaError, match="vazia"):
        versao.changelog(vazio, "1.0.1", date(2026, 9, 29))
    with pytest.raises(versao.RecusaError, match="já tem"):
        versao.changelog(CL, "1.0.0-beta.3", date(2026, 9, 29))


def test_uv_lock_usa_a_forma_pep440() -> None:
    lock = 'name = "outra"\nversion = "1.0"\n\n[[package]]\nname = "ragx"\nversion = "1.0.0b3"\n'
    assert 'name = "ragx"\nversion = "1.0.0b4"' in versao.uv_lock(lock, "1.0.0-beta.4")
    assert 'name = "outra"\nversion = "1.0"' in versao.uv_lock(lock, "1.0.0-beta.4")


def test_package_lock_troca_as_duas_versoes_do_pacote() -> None:
    lock = json.dumps({"name": "app", "version": "0.0.0", "packages": {"": {"version": "0.0.0"}, "node_modules/x": {"version": "4.5.0"}}})
    dados = json.loads(versao.package_json(lock, "1.0.0-beta.4"))
    assert dados["version"] == "1.0.0-beta.4"
    assert dados["packages"][""]["version"] == "1.0.0-beta.4"
    assert dados["packages"]["node_modules/x"]["version"] == "4.5.0"


def test_pyproject_troca_so_a_versao_do_projeto() -> None:
    texto = '[project]\nname = "ragx"\nversion = "1.0.0-beta.3"\n\n[tool.x]\nversion = "9"\n'
    assert versao.pyproject(texto, "1.0.0") == '[project]\nname = "ragx"\nversion = "1.0.0"\n\n[tool.x]\nversion = "9"\n'


@pytest.mark.parametrize("v", ["1.0", "v1.0.0-", "1.0.0 beta", "1.0.0-beta..4"])
def test_versao_que_nao_e_semver_e_recusada(v: str) -> None:
    assert versao.main([v]) == 1
