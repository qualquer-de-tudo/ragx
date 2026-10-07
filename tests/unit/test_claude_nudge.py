"""O lembrete do índice no primeiro `Grep`/`Glob` da sessão (RAGX-0160)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx import hooklight
from ragx.cli.main import app
from ragx.tokens import count_tokens

pytestmark = pytest.mark.unit
runner = CliRunner()

SEGREDO = "sk_live_51H8xQ2KZvLmNpQrStUvWxYz0123456789"


@pytest.fixture()
def casa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def _indexado(raiz: Path) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / ".ragx").mkdir(exist_ok=True)
    (raiz / ".ragx" / "knowledge.db").write_bytes(b"")
    (raiz / "ragx.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    return raiz


def _stdin(sessao: str, cwd: Path, padrao: str = "AuthService") -> str:
    return json.dumps({
        "session_id": sessao, "cwd": str(cwd), "hook_event_name": "PreToolUse",
        "tool_name": "Grep", "tool_input": {"pattern": padrao},
    })


def _nudge(entrada: str, cwd: Path, claude: bool = True) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    if claude:
        env["CLAUDECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "ragx.entry", "claude", "nudge"],
        cwd=cwd, env=env, input=entrada.encode("utf-8"), capture_output=True, check=False,
    )


def test_lembrete_do_pai_nao_silencia_subagentes(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    entrada = json.loads(_stdin("pai", raiz))
    assert b"RAGX" in _nudge(json.dumps(entrada), tmp_path).stdout
    for agente in ("a1", "a2"):
        entrada["agent_id"] = agente
        assert b"RAGX" in _nudge(json.dumps(entrada), tmp_path).stdout
        assert _nudge(json.dumps(entrada), tmp_path).stdout == b""


# ── a instalação (HOME redirecionado: nunca o `settings.json` real) ─────
def _settings(casa: Path) -> dict:
    return json.loads((casa / ".claude" / "settings.json").read_text(encoding="utf-8"))


def _pretool(casa: Path) -> list[dict]:
    return list(_settings(casa).get("hooks", {}).get("PreToolUse", []))


def test_on_instala_o_grupo_pretooluse_com_matcher_ao_lado_do_sessionstart(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    runner.invoke(app, ["claude", "on"])  # idempotente
    grupos = _pretool(casa)
    assert len(grupos) == 1 and grupos[0]["matcher"] == "Grep|Glob"
    (hook,) = grupos[0]["hooks"]
    assert hook["command"].endswith("claude nudge") and hook["timeout"] == 5
    assert "async" not in hook  # síncrono: o lembrete chega antes do resultado
    assert len(_settings(casa)["hooks"]["SessionStart"]) == 1  # a dica continua ao lado


def test_off_remove_so_o_nosso_e_preserva_os_da_pessoa(casa: Path) -> None:
    alheio = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo audit"}]}
    (casa / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [alheio]}}), encoding="utf-8")
    runner.invoke(app, ["claude", "on"])
    assert alheio in _pretool(casa) and len(_pretool(casa)) == 2
    runner.invoke(app, ["claude", "off"])
    assert _pretool(casa) == [alheio]


def test_no_nudge_nao_instala_e_remove_o_que_havia(casa: Path) -> None:
    runner.invoke(app, ["claude", "on", "--no-nudge"])
    assert _pretool(casa) == []
    runner.invoke(app, ["claude", "on"])
    assert len(_pretool(casa)) == 1
    runner.invoke(app, ["claude", "on", "--no-nudge"])
    assert _pretool(casa) == []


def test_status_json_mostra_nudge_por_perfil(casa: Path) -> None:
    runner.invoke(app, ["claude", "on"])
    estado = json.loads(runner.invoke(app, ["claude", "status", "--json"]).output)
    assert all(p["nudge"] is True and "hint" in p and "touch" in p for p in estado["profiles"])


def test_settings_quebrado_nao_e_sobrescrito(casa: Path) -> None:
    (casa / ".claude" / "settings.json").write_text("{quebrado", encoding="utf-8")
    runner.invoke(app, ["claude", "on"])
    assert (casa / ".claude" / "settings.json").read_text(encoding="utf-8") == "{quebrado"


# ── o comando ───────────────────────────────────────────────────────────
def test_a_primeira_vez_imprime_o_json_e_a_segunda_cala(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    primeira = _nudge(_stdin("s1", raiz), tmp_path)  # cwd do PROCESSO fora do projeto: vale o `cwd` do stdin
    assert primeira.returncode == 0
    saida = json.loads(primeira.stdout.decode("utf-8"))
    ctx = saida["hookSpecificOutput"]
    assert ctx["hookEventName"] == "PreToolUse" and "build_context" in ctx["additionalContext"]
    assert "permissionDecision" not in ctx  # sugere, nunca bloqueia
    assert _nudge(_stdin("s1", raiz), tmp_path).stdout == b""
    assert _nudge(_stdin("s2", raiz), tmp_path).stdout != b""  # outra sessão


def test_o_texto_cabe_em_60_tokens_e_nao_ecoa_o_tool_input(tmp_path: Path) -> None:
    assert count_tokens(hooklight.texto_lembrete()) <= 60
    raiz = _indexado(tmp_path / "proj")
    r = _nudge(_stdin("s1", raiz, padrao=SEGREDO), tmp_path)
    assert SEGREDO.encode() not in r.stdout
    log = (raiz / ".ragx" / "logs" / "cli.jsonl").read_text(encoding="utf-8")
    assert SEGREDO not in log
    (linha,) = [json.loads(x) for x in log.splitlines()]
    assert linha["command"] == "nudge" and set(linha) >= {"ts", "command", "project"}


@pytest.mark.parametrize(
    "entrada",
    ["", "isto não é json", "[]", '{"session_id": "s"}', '{"cwd": "/x"}', '{"session_id": "", "cwd": "/x"}'],
)
def test_stdin_vazio_invalido_ou_incompleto_cala_com_zero(tmp_path: Path, entrada: str) -> None:
    r = _nudge(entrada, tmp_path)
    assert r.returncode == 0 and r.stdout == b""


def test_projeto_sem_indice_cala_e_nao_cria_ragx(tmp_path: Path) -> None:
    pasta = tmp_path / "solta"
    pasta.mkdir()
    (pasta / "ragx.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    r = _nudge(_stdin("s1", pasta), tmp_path)
    assert r.returncode == 0 and r.stdout == b"" and not (pasta / ".ragx").exists()


def test_session_id_hostil_fica_preso_a_pasta_de_marcadores(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    for hostil in ("../x", r"..\..\x", "a/b/c", "y" * 500):
        _nudge(_stdin(hostil, raiz), tmp_path)
    nomes = [p.name for p in (raiz / ".ragx" / "cache" / "nudge").iterdir()]
    assert nomes and all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", n) for n in nomes)
    assert not (raiz / "x").exists() and not (raiz / ".ragx" / "x").exists()


def test_dois_simultaneos_exatamente_um_imprime(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "ragx.entry", "claude", "nudge"], cwd=tmp_path, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        for _ in range(4)
    ]
    saidas = []
    for p in procs:
        out, _ = p.communicate(_stdin("corrida", raiz).encode("utf-8"), timeout=30)
        saidas.append(out)
    assert sum(1 for o in saidas if o) == 1


def test_a_corrida_em_threads_do_marcador_so_deixa_um_passar(tmp_path: Path) -> None:
    pasta = tmp_path / "m"
    ganhou: list[bool] = []
    largada = threading.Barrier(8)

    def corre() -> None:
        largada.wait()
        ganhou.append(hooklight.primeira_vez(pasta, "sessao", None))

    fios = [threading.Thread(target=corre) for _ in range(8)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    assert ganhou.count(True) == 1


def test_marcadores_com_mais_de_7_dias_sao_apagados_ao_criar_um_novo(tmp_path: Path) -> None:
    pasta = tmp_path / "m"
    pasta.mkdir()
    velho, recente = pasta / "velho", pasta / "recente"
    velho.write_bytes(b"")
    recente.write_bytes(b"")
    antigo = time.time() - 8 * 24 * 3600
    os.utime(velho, (antigo, antigo))
    assert hooklight.primeira_vez(pasta, "nova", None) is True
    assert not velho.exists() and recente.exists() and (pasta / "nova").exists()


def test_o_nudge_nao_le_arquivo_do_projeto(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    (raiz / "dados.py").write_text(f'k = "{SEGREDO}"\n', encoding="utf-8")
    r = _nudge(_stdin("s1", raiz), tmp_path)
    assert SEGREDO.encode() not in r.stdout


def test_o_comando_da_cli_completa_tambem_funciona(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = _indexado(tmp_path / "proj")
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["claude", "nudge"], input=_stdin("cli", raiz))
    assert r.exit_code == 0 and "additionalContext" in r.output


def test_latencia_do_lembrete_dentro_do_teto(tmp_path: Path) -> None:
    raiz = _indexado(tmp_path / "proj")
    tempos = []
    for i in range(7):
        t0 = time.perf_counter()
        _nudge(_stdin(f"lat{i}", raiz), tmp_path, claude=False)
        tempos.append((time.perf_counter() - t0) * 1000)
    tempos.sort()
    assert tempos[len(tempos) // 2] < 400  # folga de CI; a medição real está na task (alvo: 120 ms p50)
