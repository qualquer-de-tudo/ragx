"""E2E da Fase 0: init -> security scan -> doctor -> size."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.secrets_under_test import FIXTURE_ROOT, MUST_BLOCK, leaked
from ragx.cli.main import app

pytestmark = pytest.mark.e2e
runner = CliRunner()


@pytest.fixture
def projeto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT, dst)
    # provider determinístico: os testes de CLI não devem depender de daemon
    monkeypatch.setenv("RAGX_EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setenv("RAGX_EMBEDDING_DIM", "128")
    monkeypatch.setenv("RAGX_EMBEDDING_VERSIONED_DIM", "64")
    # Isola o HOME: `ragx init` registra o projeto no hub local da máquina
    # (~/.ragx/hub por padrão) — sem isso, testes escreveriam no hub real
    # de quem roda a suíte e vazariam estado entre testes.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    monkeypatch.chdir(dst)
    return dst


def test_init_cria_estrutura(projeto: Path) -> None:
    r = runner.invoke(app, ["init", "."])
    assert r.exit_code == 0, r.output
    assert (projeto / "ragx.toml").exists()
    assert (projeto / ".ragx" / "knowledge.db").exists()
    assert ".ragx/" in (projeto / ".gitignore").read_text(encoding="utf-8")


def test_init_e_idempotente(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    antes = (projeto / "ragx.toml").read_text(encoding="utf-8")
    r = runner.invoke(app, ["init", "."])
    assert r.exit_code == 0
    assert (projeto / "ragx.toml").read_text(encoding="utf-8") == antes


def test_init_registra_projeto_no_hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isola o HOME para nao escrever no hub real da maquina rodando o teste.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows

    proj_dir = tmp_path / "meu-projeto"
    proj_dir.mkdir()
    monkeypatch.chdir(proj_dir)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output

    from ragx.config import load_config
    from ragx.federation import hub

    cfg = load_config(proj_dir)
    projetos = hub.list_projects(cfg)
    assert len(projetos) == 1
    assert projetos[0]["path"] == str(proj_dir.resolve())


def test_init_nao_falha_se_projeto_e_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    proj_dir = tmp_path / "projeto-privado"
    proj_dir.mkdir()
    monkeypatch.chdir(proj_dir)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    # marca como private DEPOIS do init (init cria o ragx.toml default)
    cfg_path = proj_dir / "ragx.toml"
    texto = cfg_path.read_text(encoding="utf-8").replace(
        'visibility = "workspace"', 'visibility = "private"'
    )
    cfg_path.write_text(texto, encoding="utf-8")

    # rodar init de novo (idempotente) nao deve quebrar mesmo com o projeto private
    result2 = runner.invoke(app, ["init", "--force"])
    assert result2.exit_code == 0, result2.output


def test_scan_bloqueia_e_retorna_exit_1(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    r = runner.invoke(app, ["security", "scan", "."])
    assert r.exit_code == 1, "achados críticos devem falhar o comando"
    for rel in MUST_BLOCK:
        assert rel in r.output, f"{rel} não apareceu no relatório"


def test_scan_nunca_imprime_o_segredo(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    r = runner.invoke(app, ["security", "scan", "."])
    assert leaked(r.output) == [], f"o relatório vazou: {leaked(r.output)}"


def test_scan_json_e_parseavel_e_limpo(projeto: Path) -> None:
    import json
    import re

    runner.invoke(app, ["init", "."])
    r = runner.invoke(app, ["security", "scan", ".", "--json"])
    payload = json.loads(re.sub(r"\x1b\[[0-9;]*m", "", r.output))
    assert payload["blocked"] and payload["policy"] == "strict"
    assert leaked(json.dumps(payload)) == []


def test_scan_fail_on_low_ainda_falha(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    assert runner.invoke(app, ["security", "scan", ".", "--fail-on", "low"]).exit_code == 1


def test_rules_lista_regras(projeto: Path) -> None:
    r = runner.invoke(app, ["security", "rules"])
    assert r.exit_code == 0
    assert "dotenv" in r.output and "aws-access-key-id" in r.output


def test_doctor_roda(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    r = runner.invoke(app, ["doctor"])
    assert "SQLite" in r.output and "Ruleset" in r.output


def test_size_em_projeto_novo(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    r = runner.invoke(app, ["size", "--check"])
    assert r.exit_code == 0


def test_config_show_e_set(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    assert runner.invoke(app, ["config", "show"]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "security.policy", "balanced"]).exit_code == 0
    r = runner.invoke(app, ["config", "get", "security.policy"])
    assert "balanced" in r.output


def test_config_chave_invalida_e_erro_de_uso(projeto: Path) -> None:
    r = runner.invoke(app, ["config", "get", "nao.existe"])
    assert r.exit_code != 0


# ── Fase 1 ──────────────────────────────────────────────────────────────
def test_index_e_status(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    r = runner.invoke(app, ["index", "."])
    assert r.exit_code == 0, r.output
    assert "Documents" in r.output and "Chunks" in r.output
    s = runner.invoke(app, ["status"])
    assert s.exit_code == 0 and "Índice" in s.output


def test_index_e_incremental(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    r = runner.invoke(app, ["index", ".", "--json"])
    import json
    import re

    payload = json.loads(re.sub(r"\x1b\[[0-9;]*m", "", r.output))
    assert payload["new_documents"] == 0 and payload["chunks"] == 0
    assert payload["unchanged"] > 0


def test_index_nao_imprime_segredo(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    r = runner.invoke(app, ["index", "."])
    assert leaked(r.output) == []


def test_documents_e_chunks(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    d = runner.invoke(app, ["documents"])
    assert d.exit_code == 0 and "src/app.py" in d.output
    c = runner.invoke(app, ["chunks", "--document", "src/app.py"])
    assert c.exit_code == 0 and "OrderService" in c.output


def test_chunk_mostra_conteudo(projeto: Path) -> None:
    import json
    import re

    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    raw = runner.invoke(app, ["chunks", "--document", "src/app.py", "--json"]).output
    rows = json.loads(re.sub(r"\x1b\[[0-9;]*m", "", raw))
    r = runner.invoke(app, ["chunk", rows[0]["id"]])
    assert r.exit_code == 0 and "src/app.py" in r.output


def test_arquivo_bloqueado_nao_aparece_em_documents(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    d = runner.invoke(app, ["documents", "--limit", "200"])
    for rel in MUST_BLOCK:
        assert rel not in d.output, f"{rel} apareceu na listagem"


# ── Fases 3 e 4 ─────────────────────────────────────────────────────────
def test_graph_rebuild_e_entities(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    r = runner.invoke(app, ["graph", "rebuild"])
    assert r.exit_code == 0 and "Entidades" in r.output
    e = runner.invoke(app, ["entities"])
    assert e.exit_code == 0


def test_graph_aceita_entidade_e_subcomando(projeto: Path) -> None:
    """A CLI documentada quer `rag graph rebuild` E `rag graph <entidade>`."""
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    runner.invoke(app, ["graph", "rebuild"])
    r = runner.invoke(app, ["graph", "OrderService"])
    assert r.exit_code == 0 and "OrderService" in r.output


def test_graph_entidade_inexistente_sugere(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    runner.invoke(app, ["graph", "rebuild"])
    r = runner.invoke(app, ["graph", "NaoExisteNada"])
    assert r.exit_code == 1 and "não encontrada" in r.output


def test_entities_mostra_tier_quando_confianca_menor_que_um(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ragx entities` mostra `(inferred)` ao lado da confiança de entidades
    com confidence < 1.0 — aqui, a tecnologia Redis detectada por `import`
    (confiança 0.9, camada 2/referencial), não por manifesto declarado."""
    monkeypatch.setenv("RAGX_EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setenv("RAGX_EMBEDDING_DIM", "128")
    monkeypatch.setenv("RAGX_EMBEDDING_VERSIONED_DIM", "64")
    # Isola o HOME: `ragx init` registra o projeto no hub local — sem isso,
    # este teste (fora da fixture `projeto`) escreveria no hub compartilhado
    # da sessão e colidiria (UNIQUE(name)) com outros projetos de teste.
    fake_home = tmp_path.parent / f"{tmp_path.name}-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text(
        "import redis\n\n\ndef connect():\n    return redis.Redis()\n", encoding="utf-8"
    )
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    runner.invoke(app, ["graph", "rebuild"])
    r = runner.invoke(app, ["entities"])
    assert r.exit_code == 0, r.output
    assert "inferred" in r.output


def test_context_respeita_orcamento(projeto: Path) -> None:
    import json
    import re

    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    r = runner.invoke(app, ["context", "criar pedido", "--tokens", "800", "--format", "json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(re.sub(r"\x1b\[[0-9;]*m", "", r.output))
    assert payload["estimated_tokens"] <= 800
    assert payload["fragments"]
    for f in payload["fragments"]:
        assert f["document_path"] and f["lines"][0] > 0


def test_context_nunca_vaza_segredo(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    for q in ("api key", "password", "senha do banco", "AWS_SECRET_ACCESS_KEY"):
        r = runner.invoke(app, ["context", q, "--tokens", "1500"])
        assert leaked(r.output) == [], f"vazou ao pedir contexto de {q!r}"


def test_context_explain(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    r = runner.invoke(app, ["context", "criar pedido", "--tokens", "600", "--explain"])
    assert r.exit_code == 0
    assert "Intenção detectada" in r.output and "INCLUÍDOS" in r.output


def test_context_out_grava_sem_ansi(projeto: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    destino = tmp_path / "ctx.md"
    r = runner.invoke(app, ["context", "pedido", "--tokens", "600", "--out", str(destino)])
    assert r.exit_code == 0 and destino.is_file()
    body = destino.read_text(encoding="utf-8")
    assert "\x1b[" not in body and body.startswith("# Contexto —")


def test_context_formato_invalido_e_erro_de_uso(projeto: Path) -> None:
    runner.invoke(app, ["init", "."])
    runner.invoke(app, ["index", "."])
    r = runner.invoke(app, ["context", "x", "--format", "pdf"])
    assert r.exit_code != 0
