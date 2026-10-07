"""`ragx.hooklight` e `ragx.entry`: a entrada leve dos hooks (RAGX-0143)."""

from __future__ import annotations

import json
import os
import re
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
    assert b"projeto demo indexado" in _saida("ragx.entry", raiz)


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


# ── a dica enxuta, uma vez por sessão (RAGX-0164) ───────────────────────
def _hint(cwd: Path, entrada: str = "", claude: bool = True) -> bytes:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    if claude:
        env["CLAUDECODE"] = "1"
    r = subprocess.run(
        [sys.executable, "-m", "ragx.entry", "claude", "hint"],
        cwd=cwd, env=env, input=entrada.encode("utf-8"), capture_output=True, check=False,
    )
    assert r.returncode == 0
    return r.stdout


def _hook(sessao: str, source: str = "startup") -> str:
    return json.dumps({"session_id": sessao, "hook_event_name": "SessionStart", "source": source})


def _eventos(raiz: Path) -> int:
    log = raiz / ".ragx" / "logs" / "cli.jsonl"
    return len(log.read_text(encoding="utf-8").splitlines()) if log.is_file() else 0


def test_a_dica_cabe_em_150_tokens_no_projeto_e_na_pasta_pai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx.tokens import count_tokens

    raiz = _falso(tmp_path / "ragx-painel-desktop-eletron")
    assert count_tokens(hooklight.hint_text(raiz)) <= 150

    hub = tmp_path / "hub"
    hub.mkdir()
    mono = tmp_path / "mono"
    projetos = [_falso(mono / n) for n in ("frontend", "backend")]
    (hub / "registry.json").write_text(
        json.dumps({"projects": [{"name": p.name, "path": str(p)} for p in projetos]}), encoding="utf-8"
    )
    monkeypatch.setenv("RAGX_HUB_PATH", str(hub))
    assert count_tokens(hooklight.hint_text(mono)) <= 150


def test_os_nomes_de_ferramenta_da_dica_existem_nos_dois_perfis(tmp_path: Path) -> None:
    import asyncio
    import re as _re

    from ragx.mcp.server import build_server

    raiz = _falso(tmp_path / "p")
    nomes = set(_re.findall(r"mcp__ragx__([a-z_]+)", hooklight.hint_text(raiz)))
    assert {"build_context", "search_hybrid", "get_chunk"} <= nomes
    cfg = load_config(raiz)
    for perfil in ("full", "slim"):
        expostas = {t.name for t in asyncio.run(build_server(cfg, profile=perfil).list_tools())}
        assert nomes <= expostas, (perfil, nomes - expostas)


def test_a_dica_sai_uma_vez_por_sessao_e_nao_repete_o_evento(tmp_path: Path) -> None:
    raiz = _falso(tmp_path / "proj")
    primeira = _hint(raiz, _hook("sessao-1"))
    assert b"projeto demo indexado" in primeira and _eventos(raiz) == 1
    assert _hint(raiz, _hook("sessao-1")) == b""  # subagente / repetição: calada
    assert _eventos(raiz) == 1  # e não conta a sessão de novo
    assert _hint(raiz, _hook("sessao-2")) == primeira  # outra sessão recebe
    assert _eventos(raiz) == 2


@pytest.mark.parametrize("source", ["clear", "compact", "resume"])
def test_depois_de_clear_compact_ou_resume_a_dica_volta(tmp_path: Path, source: str) -> None:
    raiz = _falso(tmp_path / "proj")
    _hint(raiz, _hook("s1"))
    assert b"RAGX" in _hint(raiz, _hook("s1", source))


def test_subagentes_recebem_contexto_sem_consumir_dica_ou_contar_sessao(tmp_path: Path) -> None:
    raiz = _falso(tmp_path / "proj")
    _hint(raiz, _hook("pai"))
    for agente in ("a1", "a2", "a1"):
        entrada = json.dumps({
            "session_id": "pai", "agent_id": agente, "cwd": str(raiz),
            "hook_event_name": "SubagentStart",
        })
        saida = json.loads(_hint(tmp_path, entrada))
        assert saida["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
        assert "ToolSearch" in saida["hookSpecificOutput"]["additionalContext"]
    assert _eventos(raiz) == 1
    assert not (tmp_path / ".ragx").exists()


def test_dica_usa_cwd_do_hook_para_orientar_e_registrar(tmp_path: Path) -> None:
    raiz = _falso(tmp_path / "proj")
    entrada = json.dumps({"session_id": "s1", "cwd": str(raiz), "hook_event_name": "SessionStart"})
    assert b"RAGX" in _hint(tmp_path, entrada)
    assert _eventos(raiz) == 1
    assert not (tmp_path / ".ragx").exists()


def test_sem_session_id_ou_com_stdin_invalido_a_dica_sai_sempre(tmp_path: Path) -> None:
    raiz = _falso(tmp_path / "proj")
    for entrada in ("", "isto não é json", "[]", '{"source": "startup"}', '{"session_id": "!!!"}'):
        assert b"RAGX" in _hint(raiz, entrada), entrada
        assert b"RAGX" in _hint(raiz, entrada), entrada  # e de novo: sem id, não há o que deduplicar


def test_session_id_hostil_fica_preso_a_pasta_de_marcadores(tmp_path: Path) -> None:
    raiz = _falso(tmp_path / "proj")
    for hostil in ("../x", r"..\..\x", "a/b/c", r"C:\x", "y" * 500):
        _hint(raiz, _hook(hostil))
    marcadores = raiz / ".ragx" / "cache" / "hint"
    nomes = sorted(p.name for p in marcadores.iterdir())
    assert nomes and all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", n) for n in nomes), nomes
    # nada foi criado fora dela
    assert not (raiz / "x").exists() and not (tmp_path / "x").exists() and not (raiz / ".ragx" / "x").exists()


def test_na_pasta_pai_o_marcador_fica_no_hub_e_nao_cria_ragx_na_pasta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hub = tmp_path / "hub"
    hub.mkdir()
    mono = tmp_path / "mono"
    filho = _falso(mono / "api")
    (hub / "registry.json").write_text(json.dumps({"projects": [{"name": "api", "path": str(filho)}]}), encoding="utf-8")
    monkeypatch.setenv("RAGX_HUB_PATH", str(hub))
    primeira = _hint(mono, _hook("s1"))
    assert b'scope="project:api"' in primeira
    assert _hint(mono, _hook("s1")) == b""
    assert (hub / "hint" / "s1").is_file() and not (mono / ".ragx").exists()


def test_o_stdin_que_nunca_fecha_nao_trava_o_hook(tmp_path: Path) -> None:
    import time as _t

    raiz = _falso(tmp_path / "proj")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    inicio = _t.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-m", "ragx.entry", "claude", "hint"],
        cwd=raiz, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    try:
        saida = proc.stdout.read()  # type: ignore[union-attr]
    finally:
        proc.stdin.close()  # type: ignore[union-attr]
        proc.wait(timeout=10)
    assert b"RAGX" in saida and _t.monotonic() - inicio < 5


def _falso(raiz: Path) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / ".ragx").mkdir(exist_ok=True)
    (raiz / ".ragx" / "knowledge.db").write_bytes(b"")
    (raiz / "ragx.toml").write_text(f'[project]\nname = "{"demo" if raiz.name == "proj" else raiz.name}"\n', encoding="utf-8")
    return raiz
