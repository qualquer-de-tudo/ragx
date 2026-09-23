"""Registro do RAGX nos clientes MCP.

O que torna este código perigoso não é a complexidade: é o que ele toca. O
arquivo de configuração do Claude Desktop pode conter dez servidores MCP que a
pessoa levou meses ajustando. Um instalador que reescreve o arquivo apaga tudo
isso, e ninguém liga o sumiço ao instalador que rodou semana passada.

Por isso a maior parte desta suíte não verifica que o RAGX foi registrado —
verifica que **o resto continuou lá**.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from ragx.clients import registry
from ragx.clients.registry import CLIENTS, Outcome, register, register_all

pytestmark = pytest.mark.integration


@pytest.fixture()
def casa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Um `$HOME` só deste teste. Sem isso, a suíte reescreve a configuração
    real de quem a roda — que é exatamente o desastre que ela investiga."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    return home


def _cliente(cid: str):
    achado = next((c for c in CLIENTS() if c.id == cid), None)
    assert achado is not None, f"cliente desconhecido: {cid}"
    return achado


def _instalar(cid: str) -> Path:
    """Finge que o cliente existe, criando o que prova a instalação dele."""
    c = _cliente(cid)
    c.config.parent.mkdir(parents=True, exist_ok=True)
    for marcador in c.markers:
        marcador.mkdir(parents=True, exist_ok=True)
    return c.config


# ── os cinco clientes prometidos ────────────────────────────────────────
@pytest.mark.parametrize(
    "cid", ["claude-desktop", "claude-code", "cursor", "windsurf", "gemini", "codex"]
)
def test_cada_cliente_suportado_pode_ser_registrado(casa: Path, cid: str) -> None:
    _instalar(cid)
    r = register(_cliente(cid))
    assert r.outcome is Outcome.CREATED, r.detail
    assert _cliente(cid).config.is_file()


def test_a_lista_cobre_os_clientes_que_o_readme_promete() -> None:
    ids = {c.id for c in CLIENTS()}
    assert {"claude-desktop", "claude-code", "cursor", "windsurf", "gemini", "codex"} <= ids


# ── instalação limpa ────────────────────────────────────────────────────
def test_instalacao_limpa_cria_a_configuracao(casa: Path) -> None:
    alvo = _instalar("cursor")
    assert not alvo.exists()

    r = register(_cliente("cursor"))
    assert r.outcome is Outcome.CREATED
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["mcpServers"]["ragx"] == {"command": "ragx", "args": ["mcp", "serve"]}


# ── idempotência ────────────────────────────────────────────────────────
def test_rodar_de_novo_nao_muda_nada(casa: Path) -> None:
    _instalar("cursor")
    primeira = register(_cliente("cursor"))
    assert primeira.outcome is Outcome.CREATED

    antes = _cliente("cursor").config.read_text(encoding="utf-8")
    segunda = register(_cliente("cursor"))

    assert segunda.outcome is Outcome.UNCHANGED
    assert segunda.backup is None, "nada mudou — não faz sentido gerar backup"
    assert _cliente("cursor").config.read_text(encoding="utf-8") == antes


def test_rodar_tres_vezes_nao_duplica_a_entrada(casa: Path) -> None:
    _instalar("cursor")
    for _ in range(3):
        register(_cliente("cursor"))

    bruto = _cliente("cursor").config.read_text(encoding="utf-8")
    dados = json.loads(bruto)
    assert list(dados["mcpServers"]) == ["ragx"]
    assert bruto.count('"ragx": {') == 1, "a entrada foi escrita mais de uma vez"


def test_mudar_o_comando_atualiza_em_vez_de_duplicar(casa: Path) -> None:
    _instalar("cursor")
    register(_cliente("cursor"))
    r = register(_cliente("cursor"), command="/opt/ragx/bin/ragx")

    assert r.outcome is Outcome.UPDATED
    dados = json.loads(_cliente("cursor").config.read_text(encoding="utf-8"))
    assert list(dados["mcpServers"]) == ["ragx"]
    assert dados["mcpServers"]["ragx"]["command"] == "/opt/ragx/bin/ragx"


# ── o que já estava lá ──────────────────────────────────────────────────
def test_outros_servidores_mcp_sao_preservados(casa: Path) -> None:
    alvo = _instalar("claude-code")
    alvo.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {"command": "gh-mcp", "args": ["--stdio"]},
                    "postgres": {"command": "pg-mcp", "args": []},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    r = register(_cliente("claude-code"))
    assert r.outcome is Outcome.UPDATED

    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["mcpServers"]["github"] == {"command": "gh-mcp", "args": ["--stdio"]}
    assert dados["mcpServers"]["postgres"] == {"command": "pg-mcp", "args": []}
    assert "ragx" in dados["mcpServers"]


def test_configuracao_fora_de_mcpservers_e_preservada(casa: Path) -> None:
    """O `~/.claude.json` guarda MUITO mais que servidores MCP."""
    alvo = _instalar("claude-code")
    alvo.write_text(
        json.dumps(
            {
                "numStartups": 42,
                "theme": "dark",
                "projects": {"/home/x/p": {"allowedTools": ["Read"]}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    register(_cliente("claude-code"))

    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["numStartups"] == 42
    assert dados["theme"] == "dark"
    assert dados["projects"]["/home/x/p"]["allowedTools"] == ["Read"]
    assert dados["mcpServers"]["ragx"]["command"] == "ragx"


def test_configuracao_parcial_sem_a_chave_de_servidores(casa: Path) -> None:
    alvo = _instalar("gemini")
    alvo.write_text(json.dumps({"theme": "GitHub"}), encoding="utf-8")

    r = register(_cliente("gemini"))
    assert r.outcome is Outcome.UPDATED
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["theme"] == "GitHub"
    assert dados["mcpServers"]["ragx"]


def test_arquivo_existente_mas_vazio(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text("", encoding="utf-8")

    r = register(_cliente("cursor"))
    assert r.ok and r.outcome is Outcome.UPDATED
    assert json.loads(alvo.read_text(encoding="utf-8"))["mcpServers"]["ragx"]


# ── backup ──────────────────────────────────────────────────────────────
def test_alterar_arquivo_existente_gera_backup(casa: Path) -> None:
    alvo = _instalar("cursor")
    original = json.dumps({"mcpServers": {"outro": {"command": "x", "args": []}}}, indent=2)
    alvo.write_text(original, encoding="utf-8")

    r = register(_cliente("cursor"))
    assert r.backup is not None and r.backup.is_file()
    assert r.backup.read_text(encoding="utf-8") == original


def test_criar_arquivo_novo_nao_gera_backup(casa: Path) -> None:
    _instalar("cursor")
    r = register(_cliente("cursor"))
    assert r.outcome is Outcome.CREATED
    assert r.backup is None, "não havia nada para salvar"


# ── cliente ausente ─────────────────────────────────────────────────────
def test_cliente_nao_instalado_e_pulado_sem_erro(casa: Path) -> None:
    # Nada foi criado: nenhum cliente existe nesta casa.
    r = register(_cliente("windsurf"))
    assert r.outcome is Outcome.ABSENT
    assert r.ok, "não ter o Windsurf instalado não é falha"
    assert not _cliente("windsurf").config.exists()


def test_nao_criamos_pasta_de_cliente_que_nao_existe(casa: Path) -> None:
    """Espalhar `~/.codeium/` por máquinas que não usam Windsurf é lixo."""
    register_all()
    assert not (casa / ".codeium").exists()
    assert not (casa / ".cursor").exists()


def test_register_all_so_falha_quando_algo_falha_de_verdade(casa: Path) -> None:
    resultados = register_all()
    assert resultados, "a lista de clientes não pode estar vazia"
    assert all(r.ok for r in resultados)
    assert all(r.outcome is Outcome.ABSENT for r in resultados)


# ── configuração inválida ───────────────────────────────────────────────
def test_json_invalido_nao_e_sobrescrito(casa: Path) -> None:
    """Pode ser o arquivo que a pessoa está editando agora."""
    alvo = _instalar("cursor")
    quebrado = '{"mcpServers": {"github": '
    alvo.write_text(quebrado, encoding="utf-8")

    r = register(_cliente("cursor"))
    assert r.outcome is Outcome.FAILED
    assert not r.ok
    assert alvo.read_text(encoding="utf-8") == quebrado, "o arquivo foi destruído"
    assert "não vou sobrescrever" in r.detail.lower()


def test_topo_que_nao_e_objeto_e_recusado(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text("[1, 2, 3]", encoding="utf-8")

    r = register(_cliente("cursor"))
    assert r.outcome is Outcome.FAILED
    assert alvo.read_text(encoding="utf-8") == "[1, 2, 3]"


def test_mcpservers_do_tipo_errado_e_recusado(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text('{"mcpServers": "nao é um objeto"}', encoding="utf-8")

    r = register(_cliente("cursor"))
    assert r.outcome is Outcome.FAILED
    assert "não vou mexer" in r.detail


# ── permissão ───────────────────────────────────────────────────────────
@pytest.mark.skipif(sys.platform == "win32", reason="chmod não restringe assim no Windows")
def test_sem_permissao_de_escrita_falha_com_mensagem(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text("{}", encoding="utf-8")
    alvo.parent.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x: não dá para criar o temporário
    try:
        r = register(_cliente("cursor"))
        assert r.outcome is Outcome.FAILED
        assert not r.ok
        assert r.detail, "falha sem explicação não ajuda ninguém"
    finally:
        alvo.parent.chmod(stat.S_IRWXU)


# ── simulação ───────────────────────────────────────────────────────────
def test_dry_run_nao_escreve_nada(casa: Path) -> None:
    alvo = _instalar("cursor")
    r = register(_cliente("cursor"), dry_run=True)
    assert r.outcome is Outcome.CREATED, "diz o que FARIA"
    assert not alvo.exists(), "mas não escreveu"
    assert r.backup is None


def test_dry_run_sobre_arquivo_existente_nao_gera_backup(casa: Path) -> None:
    alvo = _instalar("cursor")
    alvo.write_text('{"mcpServers": {}}', encoding="utf-8")
    r = register(_cliente("cursor"), dry_run=True)
    assert r.outcome is Outcome.UPDATED
    assert r.backup is None
    assert json.loads(alvo.read_text(encoding="utf-8")) == {"mcpServers": {}}


# ── Codex CLI: TOML ─────────────────────────────────────────────────────
def test_codex_grava_a_tabela_toml(casa: Path) -> None:
    alvo = _instalar("codex")
    r = register(_cliente("codex"))
    assert r.outcome is Outcome.CREATED

    import tomllib

    dados = tomllib.loads(alvo.read_text(encoding="utf-8"))
    assert dados["mcp_servers"]["ragx"] == {"command": "ragx", "args": ["mcp", "serve"]}


def test_codex_preserva_comentarios_e_outras_tabelas(casa: Path) -> None:
    """Reserializar TOML apagaria os comentários da pessoa."""
    alvo = _instalar("codex")
    alvo.write_text(
        "# minha configuração do Codex\n"
        'model = "o3"\n'
        "\n"
        "[mcp_servers.github]\n"
        'command = "gh-mcp"\n'
        "args = []\n",
        encoding="utf-8",
    )

    register(_cliente("codex"))
    texto = alvo.read_text(encoding="utf-8")

    assert "# minha configuração do Codex" in texto
    import tomllib

    dados = tomllib.loads(texto)
    assert dados["model"] == "o3"
    assert dados["mcp_servers"]["github"]["command"] == "gh-mcp"
    assert dados["mcp_servers"]["ragx"]["command"] == "ragx"


def test_codex_e_idempotente(casa: Path) -> None:
    _instalar("codex")
    register(_cliente("codex"))
    antes = _cliente("codex").config.read_text(encoding="utf-8")

    r = register(_cliente("codex"))
    assert r.outcome is Outcome.UNCHANGED
    assert _cliente("codex").config.read_text(encoding="utf-8") == antes


def test_codex_atualiza_sem_duplicar_a_tabela(casa: Path) -> None:
    alvo = _instalar("codex")
    register(_cliente("codex"))
    register(_cliente("codex"), command="/opt/ragx")

    texto = alvo.read_text(encoding="utf-8")
    assert texto.count("[mcp_servers.ragx]") == 1

    import tomllib

    assert tomllib.loads(texto)["mcp_servers"]["ragx"]["command"] == "/opt/ragx"


def test_codex_atualiza_sem_engolir_a_tabela_seguinte(casa: Path) -> None:
    """Substituir "do cabeçalho até o fim" apagaria o que vem depois."""
    alvo = _instalar("codex")
    alvo.write_text(
        "[mcp_servers.ragx]\n"
        'command = "antigo"\n'
        "args = []\n"
        "\n"
        "[mcp_servers.github]\n"
        'command = "gh-mcp"\n'
        "args = []\n",
        encoding="utf-8",
    )

    register(_cliente("codex"))

    import tomllib

    dados = tomllib.loads(alvo.read_text(encoding="utf-8"))
    assert dados["mcp_servers"]["ragx"]["command"] == "ragx"
    assert dados["mcp_servers"]["github"]["command"] == "gh-mcp", "a tabela seguinte sumiu"


def test_codex_toml_invalido_nao_e_sobrescrito(casa: Path) -> None:
    alvo = _instalar("codex")
    quebrado = "[mcp_servers.ragx\ncommand = "
    alvo.write_text(quebrado, encoding="utf-8")

    r = register(_cliente("codex"))
    assert r.outcome is Outcome.FAILED
    assert alvo.read_text(encoding="utf-8") == quebrado


# ── escrita atômica ─────────────────────────────────────────────────────
def test_nao_sobra_arquivo_temporario(casa: Path) -> None:
    alvo = _instalar("cursor")
    register(_cliente("cursor"))
    restos = list(alvo.parent.glob("*.ragx-tmp"))
    assert not restos, f"temporários deixados para trás: {restos}"


def test_detect_so_lista_o_que_existe(casa: Path) -> None:
    assert registry.detect() == []
    _instalar("cursor")
    assert [c.id for c in registry.detect()] == ["cursor"]


# ── permissões do arquivo de configuração ───────────────────────────────
# `~/.claude.json` e afins podem guardar tokens de outros servidores MCP. A
# troca atômica (temporário + os.replace) não pode trocar um arquivo 0600 por
# um 0644 criado com o umask padrão.
@pytest.mark.skipif(sys.platform == "win32", reason="bits de permissão POSIX")
def test_registrar_preserva_a_permissao_do_arquivo_existente(casa: Path) -> None:
    alvo = _instalar("claude-code")
    alvo.write_text('{"mcpServers": {}}', encoding="utf-8")
    alvo.chmod(0o600)

    r = register(_cliente("claude-code"))

    assert r.outcome is Outcome.UPDATED
    assert stat.S_IMODE(alvo.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="bits de permissão POSIX")
def test_arquivo_novo_nasce_legivel_so_pelo_dono(casa: Path) -> None:
    alvo = _instalar("claude-code")
    assert not alvo.exists()

    r = register(_cliente("claude-code"))

    assert r.outcome is Outcome.CREATED
    assert stat.S_IMODE(alvo.stat().st_mode) == 0o600


def test_escrita_copia_o_modo_do_destino_para_o_temporario(
    casa: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Roda em qualquer SO: o modo do destino vai para o temporário antes da troca."""
    alvo = _instalar("cursor")
    alvo.write_text("{}", encoding="utf-8")
    chamadas: list[tuple[Path, Path]] = []
    original = registry.shutil.copymode

    def espiao(src: Path, dst: Path) -> None:
        chamadas.append((Path(src), Path(dst)))
        original(src, dst)

    monkeypatch.setattr(registry.shutil, "copymode", espiao)

    register(_cliente("cursor"))

    assert chamadas == [(alvo, alvo.with_name(f"{alvo.name}.ragx-tmp"))]
