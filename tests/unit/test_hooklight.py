"""`ragx.hooklight` e `ragx.entry`: a entrada leve dos hooks (RAGX-0143)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ragx import hooklight
from ragx.config import load_config
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.unit

TOML = '[project]\nname = "demo"\nid = "demo"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


def _indexado(raiz: Path, toml: str = TOML) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "ragx.toml").write_text(toml, encoding="utf-8")
    (raiz / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_project(load_config(raiz), embed=False)
    return raiz


# ── paridade da configuração mínima com `load_config` ───────────────────
@pytest.mark.parametrize(
    "toml",
    [
        TOML,
        '[project]\nid = "x"\n',  # sem nome: o padrão `projeto`
        '[project]\nname = ""\n',  # nome vazio: cai no nome da pasta
        TOML + '\n[hub]\npath = "~/outro/hub"\n',
    ],
)
def test_configuracao_minima_bate_com_load_config(tmp_path: Path, toml: str) -> None:
    raiz = tmp_path / "proj"
    raiz.mkdir()
    (raiz / "ragx.toml").write_text(toml, encoding="utf-8")
    leve, cheia = hooklight.carregar(raiz), load_config(raiz)
    assert leve.root == cheia.root
    assert leve.nome == (cheia.project.name or cheia.root.name)
    assert leve.hub_dir == cheia.hub_dir
    assert leve.db_path == cheia.db_path and leve.state_dir == cheia.state_dir


def test_ambiente_vence_o_toml_como_em_load_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = tmp_path / "proj"
    raiz.mkdir()
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    monkeypatch.setenv("RAGX_PROJECT_NAME", "do-ambiente")
    monkeypatch.setenv("RAGX_HUB_PATH", str(tmp_path / "meu-hub"))
    leve, cheia = hooklight.carregar(raiz), load_config(raiz)
    assert leve.nome == cheia.project.name == "do-ambiente"
    assert leve.hub_dir == cheia.hub_dir == tmp_path / "meu-hub"


def test_config_do_usuario_entra_abaixo_do_toml(tmp_path: Path) -> None:
    usuario = Path(os.path.expanduser("~/.config/ragx/config.toml"))
    usuario.parent.mkdir(parents=True, exist_ok=True)
    usuario.write_text('[project]\nname = "do-usuario"\n\n[hub]\npath = "~/hub-do-usuario"\n', encoding="utf-8")
    raiz = tmp_path / "proj"
    raiz.mkdir()
    (raiz / "ragx.toml").write_text('[project]\nid = "x"\n', encoding="utf-8")
    leve, cheia = hooklight.carregar(raiz), load_config(raiz)
    assert leve.nome == cheia.project.name == "do-usuario"
    assert leve.hub_dir == cheia.hub_dir


# ── o texto: a mesma resposta pela entrada leve e pela CLI completa ─────
def _saida(modulo: str, cwd: Path, claude: bool = False) -> bytes:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    if claude:
        env["CLAUDECODE"] = "1"
    r = subprocess.run(
        [sys.executable, "-m", modulo, "claude", "hint"],
        cwd=cwd, env=env, capture_output=True, stdin=subprocess.DEVNULL, check=False,
    )
    assert r.returncode == 0
    return r.stdout


def test_dica_identica_byte_a_byte_em_projeto_indexado(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    assert _saida("ragx.entry", raiz) == _saida("ragx.cli.main", raiz)
    assert b"este projeto (demo)" in _saida("ragx.entry", raiz)


def test_dica_identica_em_pasta_pai_e_fora_de_projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hub = tmp_path / "hub"
    hub.mkdir()
    monkeypatch.setenv("RAGX_HUB_PATH", str(hub))
    mono = tmp_path / "mono"
    mono.mkdir()
    for nome in ("front", "back"):
        _indexado(mono / nome, TOML.replace('"demo"', f'"{nome}"'))
    (hub / "registry.json").write_text(
        json.dumps({"projects": [
            {"name": n, "path": str(mono / n)} for n in ("front", "back")
        ]}),
        encoding="utf-8",
    )
    pai = _saida("ragx.entry", mono)
    assert pai == _saida("ragx.cli.main", mono)
    assert b'scope="project:front"' in pai
    fora = tmp_path / "vazio"
    fora.mkdir()
    assert _saida("ragx.entry", fora) == _saida("ragx.cli.main", fora) == b""


def test_session_start_grava_a_mesma_linha_de_atividade(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    for modulo in ("ragx.entry", "ragx.cli.main"):
        _saida(modulo, raiz, claude=True)
    linhas = [
        json.loads(x)
        for x in (raiz / ".ragx" / "logs" / "cli.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(linhas) == 2
    a, b = ({k: v for k, v in linha.items() if k != "ts"} for linha in linhas)
    assert a == b == {"command": "session_start", "project": "demo", "client": "claude-code", "profile": "padrão"}


def test_erro_na_dica_nao_escreve_nada_e_sai_com_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd) -> None:  # type: ignore[no-untyped-def]
    raiz = tmp_path / "proj"
    raiz.mkdir()
    (raiz / "ragx.toml").write_text("isto não é toml [[[", encoding="utf-8")
    monkeypatch.chdir(raiz)
    assert hooklight.run_hint() == 0
    assert capfd.readouterr().out == ""


# ── a entrada não importa a CLI ─────────────────────────────────────────
PESADOS = ("typer", "rich", "pydantic", "numpy", "yaml", "pathspec", "ragx.config", "ragx.cli.main")


def test_hooklight_nao_carrega_modulos_pesados() -> None:
    codigo = (
        "import sys, ragx.hooklight, ragx.entry\n"
        f"pesados = {PESADOS!r}\n"
        "print([m for m in pesados if m in sys.modules])"
    )
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert r.stdout.strip() == "[]"


def test_o_caminho_de_hint_e_de_toque_completos_tambem_nao_os_carregam(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    codigo = (
        "import sys, io\n"
        "from ragx import hooklight\n"
        "hooklight.hint_text(); hooklight.record_session_start()\n"
        f"print([m for m in {PESADOS!r} if m in sys.modules], 'ragx.clients' in sys.modules, 'ragx.storage' in sys.modules)"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=raiz, capture_output=True, text=True, check=True)
    assert r.stdout.strip() == "[] False False"


# ── o despacho de `ragx.entry` ──────────────────────────────────────────
def test_o_resto_dos_comandos_vai_para_a_cli_completa(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, "-m", "ragx.entry", "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert r.returncode == 0 and "Knowledge Engine" in r.stdout
    r = subprocess.run([sys.executable, "-m", "ragx.entry", "comando-que-nao-existe"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert r.returncode != 0


def test_hook_run_sem_root_cai_na_cli_completa(tmp_path: Path) -> None:
    """Formato que a entrada leve não reconhece: a CLI completa responde, com o erro de sempre."""
    r = subprocess.run(
        [sys.executable, "-m", "ragx.entry", "hook-run", "post-commit"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    assert r.returncode != 0 and "root" in (r.stdout + r.stderr).lower()


@pytest.mark.parametrize(
    ("argv", "esperado"),
    [
        (["post-commit", "--root", "/r"], ("post-commit", Path("/r"), [])),
        (["post-checkout", "--root", "/r", "a", "b", "1"], ("post-checkout", Path("/r"), ["a", "b", "1"])),
        (["post-checkout", "a", "b", "1", "--root", "/r"], ("post-checkout", Path("/r"), ["a", "b", "1"])),
        (["post-merge", "--root=/r", "0"], ("post-merge", Path("/r"), ["0"])),
        (["post-commit"], None),
        (["--root", "/r"], None),
    ],
)
def test_parse_hook_run(argv: list[str], esperado: object) -> None:
    assert hooklight.parse_hook_run(argv) == esperado


def test_hook_run_leve_so_dispara_quando_deve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[tuple[Path, str]] = []
    monkeypatch.setattr(hooklight, "spawn_index", lambda raiz, evento: chamadas.append((raiz, evento)))
    raiz = tmp_path / "p"
    raiz.mkdir()
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    assert hooklight.run_hook(["post-commit", "--root", str(raiz)]) == 0
    assert hooklight.run_hook(["post-checkout", "A", "B", "0", "--root", str(raiz)]) == 0  # arquivo
    assert hooklight.run_hook(["evento-desconhecido", "--root", str(raiz)]) == 0
    assert hooklight.run_hook(["post-commit", "--root", str(tmp_path / "sem-toml")]) == 0
    assert hooklight.run_hook(["post-checkout", "A", "B", "1", "--root", str(raiz)]) == 0  # branch
    assert chamadas == [(raiz, "post-commit"), (raiz, "post-checkout")]


def test_hook_run_leve_nunca_falha_mesmo_se_o_spawn_quebra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def quebra(*_a: object) -> None:
        raise OSError("sem permissão")

    monkeypatch.setattr(hooklight, "spawn_index", quebra)
    raiz = tmp_path / "p"
    raiz.mkdir()
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    assert hooklight.run_hook(["post-commit", "--root", str(raiz)]) == 0


def test_touch_leve_enfileira_pela_entrada(tmp_path: Path) -> None:
    from ragx.indexing import touchq

    raiz = _indexado(tmp_path / "proj")
    entrada = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(raiz / "a.py")}})
    # `--no-drain` não existe na entrada leve: a drenagem destacada reindexa e esvazia a fila,
    # então confere o resultado final, não a fila intermediária
    r = subprocess.run(
        [sys.executable, "-m", "ragx.entry", "touch", "--stdin-json"],
        input=entrada, text=True, cwd=tmp_path, capture_output=True, check=False,
    )
    assert r.returncode == 0
    import time

    fim = time.time() + 15
    while time.time() < fim and touchq.is_pending(raiz / ".ragx"):
        time.sleep(0.2)
    assert not touchq.is_pending(raiz / ".ragx")
