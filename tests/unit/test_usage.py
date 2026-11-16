"""`ragx usage`: consumo real de tokens nas sessões do Claude Code (RAGX-0205)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx import usage as u
from ragx.cli.main import app

pytestmark = pytest.mark.unit
runner = CliRunner()

T0 = datetime.now(UTC) - timedelta(days=1)
SEGREDO_CMD = "grep -rn 'senha-super-secreta-123' src/financeiro/"
SEGREDO_PROMPT = "prompt-confidencial: refatore o modulo de cobranca"
SEGREDO_ARQUIVO = "C:/clientes/acme/contrato_secreto.txt"
SEGREDO_RESPOSTA = "resposta-do-modelo-que-nao-pode-vazar"


def _ts(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _prompt(at: float, cwd: str, texto: str = "faça x") -> dict:
    return {"type": "user", "timestamp": _ts(at), "cwd": cwd, "message": {"role": "user", "content": texto}}


def _assistant(at: float, msg_id: str, *blocks: dict, usage: dict | None = None) -> dict:
    msg: dict = {"id": msg_id, "role": "assistant", "model": "claude", "content": list(blocks)}
    if usage is not None:
        msg["usage"] = usage
    return {"type": "assistant", "timestamp": _ts(at), "message": msg}


def _use(tool_id: str, name: str, **entrada: object) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": entrada}


def _result(at: float, tool_id: str, content: object) -> dict:
    return {
        "type": "user",
        "timestamp": _ts(at),
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": content}]},
    }


def _hook(at: float, evento: str, texto: str) -> dict:
    return {
        "type": "attachment",
        "timestamp": _ts(at),
        "attachment": {"type": "hook_additional_context", "content": [texto], "hookEvent": evento},
    }


def _usage(inp: int, read: int, created: int, out: int) -> dict:
    return {
        "input_tokens": inp, "cache_read_input_tokens": read,
        "cache_creation_input_tokens": created, "output_tokens": out,
    }


def _write(path: Path, records: list[dict | str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    linhas = [r if isinstance(r, str) else json.dumps(r) for r in records]
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return path


# ── um arquivo ──────────────────────────────────────────────────────────
def test_mensagem_repetida_por_id_conta_uma_vez_e_linha_invalida_e_ignorada(tmp_path: Path) -> None:
    uso = _usage(10, 1000, 200, 50)
    f = _write(tmp_path / "s.jsonl", [
        _prompt(0, "C:/p"),
        "{isto não é json",
        # a mesma mensagem em três registros (um por bloco), com o mesmo uso
        _assistant(1, "m1", {"type": "thinking", "thinking": "..."}, usage=uso),
        _assistant(1, "m1", {"type": "text", "text": "ok"}, usage=uso),
        _assistant(1, "m1", _use("t1", "Grep", pattern="x"), usage=uso),
        '["lista", "não objeto"]',
        _result(2, "t1", "a.py:1: x"),
        _assistant(3, "m2", {"type": "text", "text": "pronto"}, usage=_usage(5, 2000, 0, 30)),
        "",
    ])
    a = u.analisar_arquivo(f)
    assert a.uso.turns == 2
    assert (a.uso.input_tokens, a.uso.cache_read_tokens, a.uso.cache_creation_tokens, a.uso.output_tokens) == (
        15, 3000, 200, 80,
    )
    assert a.uso.search_calls == 1
    assert a.uso.search_result_chars == len("a.py:1: x")
    assert a.uso.prompts == 1


def test_uso_parcial_de_streaming_vale_o_maior(tmp_path: Path) -> None:
    f = _write(tmp_path / "s.jsonl", [
        _assistant(1, "m1", {"type": "text", "text": "a"}, usage=_usage(3, 100, 0, 1)),
        _assistant(1, "m1", {"type": "text", "text": "b"}, usage=_usage(3, 100, 0, 40)),
    ])
    a = u.analisar_arquivo(f)
    assert a.uso.output_tokens == 40
    assert a.uso.turns == 1


def test_mensagem_sintetica_nao_e_turno(tmp_path: Path) -> None:
    sint = _assistant(1, "x", {"type": "text", "text": "API Error"}, usage=_usage(0, 0, 0, 0))
    sint["message"]["model"] = "<synthetic>"
    a = u.analisar_arquivo(_write(tmp_path / "s.jsonl", [sint]))
    assert a.uso.turns == 0


def test_leitura_de_imagem_fica_fora_do_tamanho_de_leitura(tmp_path: Path) -> None:
    f = _write(tmp_path / "s.jsonl", [
        _assistant(1, "m1", _use("r1", "Read", file_path="a.py"), _use("r2", "Read", file_path="tela.PNG"),
                   _use("r3", "Read", file_path="sem_extensao")),
        _result(2, "r1", "x = 1\n"),
        _result(2, "r2", [{"type": "image", "source": {"type": "base64", "data": "A" * 50_000}}]),
        # Read sem extensão de imagem que devolveu imagem: também não é leitura de texto
        _result(2, "r3", [{"type": "image", "source": {"data": "B" * 9_000}}, {"type": "text", "text": "zzz"}]),
    ])
    a = u.analisar_arquivo(f)
    assert a.uso.read_calls == 1
    assert a.uso.image_reads == 2
    assert a.uso.read_result_chars == len("x = 1\n")


@pytest.mark.parametrize(
    ("comando", "esperado"),
    [
        ("grep -rn foo src/", "search"),
        ("cd src && rg -n 'x' | head -20", "search"),
        ("git grep -n Foo", "search"),
        ("find . -name '*.py'", "search"),
        ("ls -la", "search"),
        ("Get-ChildItem -Recurse | Select-String 'x'", "search"),
        ("FOO=1 /usr/bin/grep x y", "search"),
        ("cat src/a.py", "read"),
        ("head -50 a.py && tail -5 b.py", "read"),
        ("sed -n '1,40p' a.py", "read"),
        ("Get-Content a.ps1", "read"),
        ("sed -i 's/a/b/' a.py", "other"),
        ("npm test", "other"),
        ("uv run pytest -q", "other"),
    ],
)
def test_categoria_do_bash(comando: str, esperado: str) -> None:
    assert u.categoria("Bash", {"command": comando}) == esperado


def test_categorias_das_ferramentas() -> None:
    assert u.categoria("mcp__ragx__build_context", {"query": "x"}) == "ragx"
    assert u.categoria("Glob", {"pattern": "*.py"}) == "search"
    assert u.categoria("Read", {"file_path": "a.md"}) == "read"
    assert u.categoria("Read", {"file_path": "doc.pdf"}) == "image"
    assert u.categoria("PowerShell", {"command": "Select-String x a.txt"}) == "search"
    assert u.categoria("Edit", {"file_path": "a.py"}) == "other"
    assert u.categoria("Bash", None) == "other"


def test_lembrete_dica_e_ragx_depois_do_lembrete(tmp_path: Path) -> None:
    f = _write(tmp_path / "s.jsonl", [
        {"type": "attachment", "timestamp": _ts(0), "attachment": {
            "type": "hook_success", "hookEvent": "SessionStart", "stdout": "RAGX: projeto x indexado. ...",
            "content": ""}},
        _assistant(1, "m1", _use("g", "Grep", pattern="x")),
        _hook(1.5, "PreToolUse", "RAGX: este projeto está indexado. mcp__ragx__build_context(query) ..."),
        _result(2, "g", "a"),
        _assistant(3, "m2", _use("r", "mcp__ragx__build_context", query="x")),
        _result(4, "r", [{"type": "text", "text": "contexto"}]),
    ])
    a = u.analisar_arquivo(f)
    assert a.hinted
    assert a.reminded_at == _ts(1.5)
    assert a.ragx_last_at == _ts(3)
    assert a.uso.ragx_calls == 1
    assert a.uso.ragx_result_chars == len("contexto")


def test_hook_de_outra_ferramenta_nao_e_lembrete(tmp_path: Path) -> None:
    a = u.analisar_arquivo(_write(tmp_path / "s.jsonl", [_hook(0, "PreToolUse", "lint: formate antes")]))
    assert a.reminded_at is None and not a.hinted


# ── sessões, perfis, projetos ───────────────────────────────────────────
def _sessao(perfil_dir: Path, sid: str, cwd: str, *extra: dict, at: float = 0) -> Path:
    pasta = perfil_dir / "projects" / "qualquer-nome"
    return _write(pasta / f"{sid}.jsonl", [
        _prompt(at, cwd),
        _assistant(at + 1, f"{sid}-m1", *extra, usage=_usage(1, 100, 10, 5)),
    ])


def test_subagente_soma_na_sessao_e_janela_filtra_pelo_inicio(tmp_path: Path) -> None:
    perfil = tmp_path / ".claude"
    _sessao(perfil, "s1", "C:/p", _use("a", "Grep"))
    _write(perfil / "projects" / "qualquer-nome" / "s1" / "subagents" / "agent-1.jsonl", [
        {"type": "user", "timestamp": _ts(2), "cwd": "C:/p", "message": {"role": "user", "content": "tarefa"}},
        _assistant(3, "sub-m1", _use("b", "Read", file_path="x.py"), usage=_usage(2, 300, 0, 7)),
    ])
    # sessão antiga: fora da janela de 1 dia contado a partir de T0
    _sessao(perfil, "velha", "C:/p", at=-5 * 86400)
    sessoes = u.coletar(T0 - timedelta(hours=1), [("padrão", perfil)], cache=None)
    assert [s.session for s in sessoes] == ["s1"]
    s = sessoes[0]
    assert s.uso.turns == 2
    assert s.uso.cache_read_tokens == 400
    assert (s.uso.search_calls, s.uso.read_calls) == (1, 1)
    assert s.uso.prompts == 1  # o prompt do subagente vem do agente, não da pessoa


def test_projeto_pela_pasta_raiz_worktree_interna_e_externa(tmp_path: Path) -> None:
    raiz = tmp_path / "repo"
    (raiz / ".git" / "worktrees" / "wt").mkdir(parents=True)
    externa = tmp_path / "fora" / "wt"
    externa.mkdir(parents=True)
    (externa / ".git").write_text(f"gitdir: {raiz / '.git' / 'worktrees' / 'wt'}\n", encoding="utf-8")
    aninhado = raiz / "pacotes" / "web"
    aninhado.mkdir(parents=True)
    projetos = [
        {"id": "p1", "name": "repo", "path": str(raiz)},
        {"id": "p2", "name": "web", "path": str(aninhado)},
    ]
    perfil = tmp_path / ".claude"
    _sessao(perfil, "raiz", str(raiz / "src"))
    _sessao(perfil, "interna", str(raiz / ".claude" / "worktrees" / "x"))
    _sessao(perfil, "externa", str(externa / "sub"))
    _sessao(perfil, "web", str(aninhado))
    _sessao(perfil, "outra", str(tmp_path / "outro-projeto"))
    sessoes = u.coletar(T0 - timedelta(hours=1), [("padrão", perfil)], cache=None)
    dono = {s.session: (u.projeto_de(s, projetos) or {}).get("id") for s in sessoes}
    assert dono == {"raiz": "p1", "interna": "p1", "externa": "p1", "web": "p2", "outra": None}


def test_relatorio_medianas_com_e_sem_ragx_e_adocao(tmp_path: Path) -> None:
    perfil = tmp_path / ".claude"
    raiz = tmp_path / "repo"
    _sessao(perfil, "a", str(raiz), _use("1", "mcp__ragx__search_hybrid"))
    _sessao(perfil, "b", str(raiz), _use("2", "Grep"), _use("3", "Grep"))
    _sessao(perfil, "c", str(raiz), _use("4", "Grep"))
    since = T0 - timedelta(hours=1)
    sessoes = u.coletar(since, [("padrão", perfil)], cache=None)
    rel = u.relatorio(sessoes, [{"id": "p1", "name": "repo", "path": str(raiz)}], 14, since, [("padrão", perfil)])
    (p,) = rel["projects"]
    assert p["sessions"] == 3
    assert p["with_ragx"]["sessions"] == 1 and p["without_ragx"]["sessions"] == 2
    assert p["without_ragx"]["median"]["search_calls"] == 1.5
    assert p["with_ragx"]["median"]["ragx_calls"] == 1
    assert p["adoption"] == {"sessions": 3, "with_ragx": 1, "hinted": 0, "reminded": 0, "ragx_after_reminder": 0}
    assert rel["kind"] == "observation"
    assert rel["overall"]["sessions"] == 3
    assert rel["profiles"] == [{"name": "padrão", "sessions": 3}]


def test_cache_reaproveita_e_invalida_quando_o_arquivo_muda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    perfil = tmp_path / ".claude"
    f = _sessao(perfil, "s1", "C:/p", _use("a", "Grep"))
    cache = tmp_path / "cache.json"
    since = T0 - timedelta(hours=1)
    assert u.coletar(since, [("padrão", perfil)], cache=cache)[0].uso.search_calls == 1

    chamadas: list[Path] = []
    original = u.analisar_arquivo

    def contando(path: Path, *a: object, **k: object) -> u.Arquivo:
        chamadas.append(path)
        return original(path, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(u, "analisar_arquivo", contando)
    assert u.coletar(since, [("padrão", perfil)], cache=cache)[0].uso.search_calls == 1
    assert chamadas == []  # veio do cache

    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_assistant(5, "m9", _use("b", "Glob"))) + "\n")
    assert u.coletar(since, [("padrão", perfil)], cache=cache)[0].uso.search_calls == 2
    assert chamadas == [f]


# ── CLI e privacidade ───────────────────────────────────────────────────
@pytest.fixture()
def casa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def _registrar(home: Path, raiz: Path) -> None:
    hub = home / ".ragx" / "hub"
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "registry.json").write_text(
        json.dumps({"schema_version": 1, "projects": [{"id": "p1", "name": "repo", "path": str(raiz)}]}),
        encoding="utf-8",
    )


def _sessao_sensivel(home: Path, raiz: Path, perfil: str = ".claude") -> None:
    _write(home / perfil / "projects" / "x" / "sens.jsonl", [
        _prompt(0, str(raiz), SEGREDO_PROMPT),
        _assistant(1, "m1", {"type": "text", "text": SEGREDO_RESPOSTA},
                   _use("b", "Bash", command=SEGREDO_CMD), _use("r", "Read", file_path=SEGREDO_ARQUIVO),
                   usage=_usage(3, 900, 50, 20)),
        _result(2, "b", f"{SEGREDO_ARQUIVO}:1: senha-super-secreta-123"),
        _result(2, "r", "conteudo do contrato"),
    ])


def test_cli_json_so_numeros_nada_do_transcript(casa: Path, tmp_path: Path) -> None:
    raiz = tmp_path / "repo"
    raiz.mkdir()
    _registrar(casa, raiz)
    _sessao_sensivel(casa, raiz)
    r = runner.invoke(app, ["usage", "--days", "7", "--json"])
    assert r.exit_code == 0, r.output
    dados = json.loads(r.output)
    (p,) = dados["projects"]
    assert p["id"] == "p1" and p["sessions"] == 1
    assert p["all"]["total"]["search_calls"] == 1 and p["all"]["total"]["read_calls"] == 1
    assert p["all"]["total"]["cache_read_tokens"] == 900
    cache = (casa / ".ragx" / "cache" / "usage-claude.json").read_text(encoding="utf-8")
    for texto in (r.output, cache):
        for segredo in ("senha-super-secreta", "financeiro", SEGREDO_PROMPT, SEGREDO_RESPOSTA, "contrato_secreto", "acme"):
            assert segredo not in texto
    # o cache não guarda a pasta da sessão, só hashes
    assert str(raiz) not in cache and raiz.as_posix() not in cache


def test_cli_le_os_perfis_extras_e_o_texto_humano(casa: Path, tmp_path: Path) -> None:
    raiz = tmp_path / "repo"
    raiz.mkdir()
    _registrar(casa, raiz)
    extra = casa / ".claude-empresa"
    extra.mkdir()
    (extra / ".claude.json").write_text("{}", encoding="utf-8")
    _sessao_sensivel(casa, raiz, perfil=".claude-empresa")
    r = runner.invoke(app, ["usage", "--json"])
    dados = json.loads(r.output)
    assert {"name": "empresa", "sessions": 1} in dados["profiles"]
    assert dados["projects"][0]["profiles"] == {"empresa": 1}

    r = runner.invoke(app, ["usage"])
    assert r.exit_code == 0, r.output
    assert "Consumo real" in r.output and "Observação, não experimento" in r.output
    assert "senha-super-secreta" not in r.output and SEGREDO_PROMPT not in r.output


def test_cli_project_fora_do_registro(casa: Path, tmp_path: Path) -> None:
    raiz = tmp_path / "solto"
    raiz.mkdir()
    _sessao_sensivel(casa, raiz)
    r = runner.invoke(app, ["usage", "--project", str(raiz), "--json", "--no-cache"])
    dados = json.loads(r.output)
    (p,) = dados["projects"]
    assert p["id"] is None and p["name"] == "solto" and p["sessions"] == 1
    assert not (casa / ".ragx" / "cache" / "usage-claude.json").exists()
