"""`ragx security scan --cached` dá o MESMO resultado que a varredura completa (RAGX-0206).

O modo com cache só pula a leitura do que o índice já examinou e não mudou; o que muda, é novo ou foi bloqueado
depois é lido como sempre. A prova é a equivalência: depois de indexar, e depois de cada tipo de mudança, o JSON
(arquivos bloqueados, censurados, ignorados e quantos foram vistos) é igual nos dois modos.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fixtures.secrets_under_test import FIXTURE_ROOT, leaked
from ragx.cli.main import app

pytestmark = pytest.mark.integration
runner = CliRunner()


@pytest.fixture
def projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT, dst)
    for k, v in {"RAGX_EMBEDDING_PROVIDER": "hashing", "RAGX_EMBEDDING_DIM": "128",
                 "RAGX_EMBEDDING_VERSIONED_DIM": "64"}.items():
        monkeypatch.setenv(k, v)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(dst)
    assert runner.invoke(app, ["init", "."]).exit_code == 0
    assert runner.invoke(app, ["index", ".", "--quiet"]).exit_code == 0
    return dst


def _scan(*extra: str) -> dict:
    r = runner.invoke(app, ["security", "scan", ".", "--json", "--fail-on", "critical", *extra])
    assert r.output.strip(), r.output
    return json.loads(r.output)


def _comparavel(d: dict) -> dict:
    """Tudo que o scan diz, menos como ele chegou lá (`mode`, `reused`)."""
    return {
        "scanned": d["scanned"], "skipped": d["skipped"], "policy": d["policy"], "ruleset": d["ruleset"],
        "blocked": sorted(d["blocked"], key=lambda b: b["path"]),
        "redacted": sorted(d["redacted"], key=lambda b: b["path"]),
    }


def test_depois_de_indexar_o_scan_com_cache_e_igual_ao_completo_e_nao_le_quase_nada(projeto: Path) -> None:
    completo, cache = _scan(), _scan("--cached")
    assert cache["mode"] == "cache" and completo["mode"] == "full"
    assert _comparavel(cache) == _comparavel(completo)
    assert completo["blocked"], "a fixture tem de ter segredo bloqueado, senão o teste não prova nada"
    assert cache["reused"] > 0


def test_o_scan_com_cache_nunca_imprime_o_segredo(projeto: Path) -> None:
    r = runner.invoke(app, ["security", "scan", ".", "--json", "--cached", "--fail-on", "critical"])
    assert not leaked(r.output)


def test_arquivo_novo_com_segredo_aparece_no_scan_com_cache(projeto: Path) -> None:
    (projeto / "novo.py").write_text('API = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    cache, completo = _scan("--cached"), _scan()
    assert any(b["path"] == "novo.py" for b in completo["blocked"])
    assert _comparavel(cache) == _comparavel(completo)


def test_arquivo_alterado_depois_do_indice_e_lido_de_novo(projeto: Path) -> None:
    alvo = next(p for p in projeto.rglob("*.py") if p.name != "novo.py")
    alvo.write_text(alvo.read_text(encoding="utf-8") + '\nTOKEN = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    cache, completo = _scan("--cached"), _scan()
    assert _comparavel(cache) == _comparavel(completo)


def test_arquivo_apagado_some_do_scan_com_cache(projeto: Path) -> None:
    bloqueado = _scan()["blocked"][0]["path"]
    (projeto / bloqueado).unlink()
    cache, completo = _scan("--cached"), _scan()
    assert all(b["path"] != bloqueado for b in cache["blocked"])
    assert _comparavel(cache) == _comparavel(completo)


def test_regra_desligada_invalida_o_cache_e_volta_para_a_varredura_completa(projeto: Path) -> None:
    toml = projeto / "ragx.toml"
    # `min_entropy` entra no contexto do veredito: mexer nele muda o que o Gate decide, então o cache não vale mais
    toml.write_text(toml.read_text(encoding="utf-8").replace('policy = "strict"', 'policy = "strict"\nmin_entropy = 4.9'), encoding="utf-8")
    cache, completo = _scan("--cached"), _scan()
    assert cache["mode"].startswith("full")
    assert _comparavel(cache) == _comparavel(completo)


def test_sem_indice_o_modo_cache_varre_tudo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT, dst)
    monkeypatch.chdir(dst)
    d = _scan("--cached")
    assert d["mode"].startswith("full") and d["reused"] == 0 and d["scanned"] > 0


def test_eventos_apagados_forcam_a_leitura_em_vez_de_esconder_o_achado(projeto: Path) -> None:
    from ragx.config import load_config
    from ragx.storage.db import open_db

    esperado = _comparavel(_scan())
    with open_db(load_config(projeto).db_path) as conn:
        conn.execute("DELETE FROM security_events")
        conn.commit()
    assert _comparavel(_scan("--cached")) == esperado


def test_staged_so_examina_os_arquivos_do_stage_e_sem_git_varre_tudo(
    projeto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from ragx.cli.commands import security as sec

    subprocess.run(["git", "init", "-q"], cwd=projeto, check=True)
    (projeto / "limpo.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "limpo.py"], cwd=projeto, check=True)
    d = _scan("--staged")
    assert d["scanned"] == 1 and d["blocked"] == []
    # o git falhou: sem lista confiável não pode virar "nada a varrer"
    monkeypatch.setattr(sec, "_staged_files", lambda root: None)
    assert _scan("--staged")["scanned"] > 1
