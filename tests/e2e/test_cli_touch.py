"""`ragx touch`: o hook `PostToolUse` enfileira o arquivo editado e a drenagem o reindexa."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.config import load_config
from ragx.indexing import touchq
from ragx.indexing.pipeline import index_project
from ragx.search.service import search

pytestmark = pytest.mark.e2e

runner = CliRunner()
TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


def _projeto(raiz: Path) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    (raiz / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_project(load_config(raiz))
    return raiz


def _hook(tool: str, caminho: str, campo: str = "file_path") -> str:
    return json.dumps({
        "session_id": "s", "cwd": "x", "hook_event_name": "PostToolUse",
        "tool_name": tool, "tool_input": {campo: caminho},
    })


@pytest.mark.parametrize(
    ("tool", "campo"),
    [("Edit", "file_path"), ("Write", "file_path"), ("MultiEdit", "file_path"),
     ("NotebookEdit", "notebook_path")],
)
def test_stdin_de_cada_ferramenta_enfileira_o_arquivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str, campo: str
) -> None:
    raiz = _projeto(tmp_path / "p")
    monkeypatch.chdir(tmp_path)  # cwd FORA do projeto
    r = runner.invoke(app, ["touch", "--stdin-json", "--no-drain"],
                      input=_hook(tool, str(raiz / "a.py"), campo))
    assert r.exit_code == 0, r.output
    assert touchq.pending(load_config(raiz).state_dir) == ["a.py"]


def test_a_raiz_vem_do_arquivo_editado_nao_do_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sessão pode estar numa pasta-pai com vários projetos."""
    um = _projeto(tmp_path / "ws" / "um")
    dois = _projeto(tmp_path / "ws" / "dois")
    monkeypatch.chdir(tmp_path / "ws")
    runner.invoke(app, ["touch", "--stdin-json", "--no-drain"], input=_hook("Edit", str(dois / "a.py")))
    assert touchq.pending(load_config(dois).state_dir) == ["a.py"]
    assert touchq.pending(load_config(um).state_dir) == []


@pytest.mark.parametrize("entrada", ["", "isto não é json", "[]", '{"tool_input": 5}', '{"tool_input": {}}'])
def test_entrada_lixo_sai_com_zero_e_nao_enfileira(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrada: str) -> None:
    raiz = _projeto(tmp_path / "p")
    monkeypatch.chdir(raiz)
    r = runner.invoke(app, ["touch", "--stdin-json", "--no-drain"], input=entrada)
    assert r.exit_code == 0
    assert touchq.pending(load_config(raiz).state_dir) == []


def test_pasta_sem_ragx_e_arquivo_fora_do_projeto_saem_com_zero_sem_efeito(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz = _projeto(tmp_path / "p")
    solto = tmp_path / "solto"
    solto.mkdir()
    (solto / "x.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(solto)
    assert runner.invoke(app, ["touch", "--stdin-json", "--no-drain"],
                         input=_hook("Edit", str(solto / "x.py"))).exit_code == 0
    assert not (solto / ".ragx").exists()
    # arquivo de OUTRO lugar apontado com --root do projeto: escapa da raiz e é recusado
    runner.invoke(app, ["touch", str(solto / "x.py"), "--root", str(raiz), "--no-drain"])
    assert touchq.pending(load_config(raiz).state_dir) == []


def test_projeto_sem_indice_nao_ganha_ragx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["touch", "a.py", "--no-drain"]).exit_code == 0
    assert not (tmp_path / ".ragx").exists()


def test_o_estado_do_ragx_nao_e_enfileirado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = _projeto(tmp_path / "p")
    monkeypatch.chdir(raiz)
    runner.invoke(app, ["touch", ".ragx/status.json", "--no-drain"])
    assert touchq.pending(load_config(raiz).state_dir) == []


def test_touch_mais_drain_deixa_o_texto_novo_buscavel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = _projeto(tmp_path / "p")
    cfg = load_config(raiz)
    (raiz / "a.py").write_text("def a():\n    return 'palavraexclusivaxyz'\n", encoding="utf-8")
    assert not search(cfg, "palavraexclusivaxyz", mode="keyword").results  # antes do touch: não acha

    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["touch", "--stdin-json", "--no-drain"], input=_hook("Edit", str(raiz / "a.py")))
    r = runner.invoke(app, ["touch", "--drain", "--root", str(raiz)])
    assert r.exit_code == 0, r.output
    assert search(cfg, "palavraexclusivaxyz", mode="keyword").results
    assert touchq.pending(cfg.state_dir) == []


def test_search_e_context_drenam_a_fila_antes_de_responder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = _projeto(tmp_path / "p")
    cfg = load_config(raiz)
    monkeypatch.chdir(raiz)
    (raiz / "a.py").write_text("def a():\n    return 'cliexclusivaqq'\n", encoding="utf-8")
    touchq.enqueue(cfg.state_dir, ["a.py"])
    r = runner.invoke(app, ["search", "cliexclusivaqq", "--mode", "keyword", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    assert dados["results"] and "stale_paths" not in dados
    assert touchq.pending(cfg.state_dir) == []


def test_search_json_traz_stale_paths_quando_nao_deu_para_drenar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ragx.core.errors import IndexBusyError
    from ragx.indexing import pipeline

    raiz = _projeto(tmp_path / "p")
    cfg = load_config(raiz)
    monkeypatch.chdir(raiz)

    def ocupado(*_a: object, **_k: object) -> None:
        raise IndexBusyError("ocupado")

    monkeypatch.setattr(pipeline, "index_paths", ocupado)
    touchq.enqueue(cfg.state_dir, ["a.py", ".env"])
    r = runner.invoke(app, ["search", "a", "--mode", "keyword", "--json"])
    dados = json.loads(r.output)
    assert dados["stale_paths"] == ["a.py"] and dados["stale_count"] == 1  # `.env` nunca aparece
