"""Fase 9 — serialização estável, reidratação e sync."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import BudgetExceededError
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project, status
from ragx.sync import serialize
from ragx.sync.rehydrate import rehydrate
from ragx.sync.service import sync

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios via SSO."""

    def login(self, credentials):
        """Valida o token e cria a sessao."""
        return self.sso.validate(credentials)

    def refresh(self, token):
        """Renova a sessao existente no cache."""
        self.cache.touch(token)
        return token
'''

DOC = "# Autenticacao\n\n## Fluxo\n\nO AuthService valida o token no provedor.\n"


def _make(root: Path) -> Path:
    (root / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (root / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "doc.md").write_text(DOC, encoding="utf-8")
    return root


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    root = _make(tmp_path)
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    serialize.serialize(cfg)
    return root


# ── serialização ────────────────────────────────────────────────────────
def test_chunks_nao_carregam_conteudo(proj: Path) -> None:
    """A decisão central do ADR-0010: conteúdo é redundante, já está no repo."""
    for p in (proj / "knowledge" / "chunks").glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            assert "content" not in json.loads(line), f"{p.name} versionou conteúdo"


def test_artefatos_tem_o_que_precisa_para_reidratar(proj: Path) -> None:
    chunks = serialize.read_chunks(load_config(proj), "auth.py")
    assert chunks
    for c in chunks:
        assert c["lines"][0] > 0 and c["content_hash"]


def test_serializacao_e_estavel(proj: Path) -> None:
    """Sem isso, `git diff knowledge/` nunca fecha."""
    cfg = load_config(proj)
    antes = {
        p.relative_to(proj).as_posix(): p.read_bytes()
        for p in (proj / "knowledge").rglob("*") if p.is_file()
    }
    serialize.serialize(cfg)
    depois = {
        p.relative_to(proj).as_posix(): p.read_bytes()
        for p in (proj / "knowledge").rglob("*") if p.is_file()
    }
    mudou = [
        k for k in antes
        if k not in ("knowledge/manifest.json",) and antes[k] != depois.get(k)
    ]
    assert mudou == [], f"artefatos instáveis: {mudou}"


def test_sem_crlf(proj: Path) -> None:
    for p in (proj / "knowledge").rglob("*.json*"):
        assert b"\r\n" not in p.read_bytes(), f"{p.name} tem CRLF"


def test_embeddings_shardados_por_prefixo(proj: Path) -> None:
    shards = list((proj / "knowledge" / "embeddings").glob("shard-*.i8"))
    assert len(shards) == 16
    manifest = json.loads(
        (proj / "knowledge" / "embeddings" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["versioned_dim"] == 64 and manifest["count"] > 0


def test_alteracao_muda_um_shard_apenas(proj: Path) -> None:
    """O critério que torna o histórico do Git barato."""
    cfg = load_config(proj)
    antes = {
        p.name: p.read_bytes() for p in (proj / "knowledge" / "embeddings").glob("shard-*.i8")
    }
    (proj / "novo.md").write_text("# Novo\n\nOutro assunto qualquer aqui.\n", encoding="utf-8")
    index_project(cfg)
    serialize.serialize(cfg)
    depois = {
        p.name: p.read_bytes() for p in (proj / "knowledge" / "embeddings").glob("shard-*.i8")
    }
    mudaram = [k for k in antes if antes[k] != depois.get(k)]
    assert 1 <= len(mudaram) <= 2, f"{len(mudaram)} shards mudaram (esperado 1-2)"


def test_documento_removido_some_dos_artefatos(proj: Path) -> None:
    cfg = load_config(proj)
    assert (proj / "knowledge" / "documents" / "doc.md.json").is_file()
    (proj / "doc.md").unlink()
    index_project(cfg)
    r = serialize.serialize(cfg)
    assert not (proj / "knowledge" / "documents" / "doc.md.json").is_file()
    assert r.removed > 0


def test_orcamento_recusa_antes_de_escrever(tmp_path: Path) -> None:
    root = _make(tmp_path)
    cfg = load_config(root)
    index_project(cfg)
    cfg.size.max_chunks = 1
    with pytest.raises(BudgetExceededError):
        serialize.serialize(cfg)


@pytest.mark.parametrize(
    "rel,esperado",
    [("a.py", "a.py"), ("src/a/b.py", "src__a__b.py"), ("docs/x.md", "docs__x.md")],
)
def test_nome_do_artefato(rel: str, esperado: str) -> None:
    assert serialize.artifact_name(rel) == esperado


def test_colisao_de_nome_e_desambiguada() -> None:
    a = serialize.artifact_name("a/b.py")
    b = serialize.artifact_name("a__b.py")
    assert a != b


# ── reidratação ─────────────────────────────────────────────────────────
def test_reidrata_do_working_tree(proj: Path) -> None:
    hydrated, report = rehydrate(load_config(proj))
    assert report.total > 0
    assert report.ok == report.total, f"{report.mismatch} mismatch, {report.missing} missing"
    assert all(h.content for h in hydrated)


def test_conteudo_reidratado_bate_com_o_indice(proj: Path) -> None:
    from ragx.storage.db import open_db

    cfg = load_config(proj)
    hydrated, _ = rehydrate(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        indexado = {r["id"]: r["content"] for r in conn.execute("SELECT id, content FROM chunks")}
    for h in hydrated:
        assert h.content == indexado[h.chunk_id], f"divergiu em {h.rel_path}:{h.start_line}"


def test_arquivo_modificado_vira_rederivacao(proj: Path) -> None:
    (proj / "auth.py").write_text(AUTH.replace("SSO", "OAuth2 corporativo"), encoding="utf-8")
    _h, report = rehydrate(load_config(proj))
    assert report.mismatch > 0
    assert "auth.py" in report.rederive


def test_arquivo_ausente_e_reportado_nao_silenciado(proj: Path) -> None:
    (proj / "doc.md").unlink()
    _h, report = rehydrate(load_config(proj))
    assert report.missing > 0
    assert any(why == "file_missing" for _cid, why in report.dropped)


def test_arquivo_que_virou_sensivel_e_bloqueado_na_reidratacao(proj: Path) -> None:
    """Re-scan no sync: arquivo já indexado pode ter virado sensível."""
    (proj / "auth.py").write_text(
        AUTH + '\nAWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8"
    )
    _h, report = rehydrate(load_config(proj))
    assert report.blocked > 0


def test_chunk_sintetico_nao_conta_como_divergencia(proj: Path) -> None:
    """Cabeçalho de classe carrega a lista de métodos: não é fatia literal.
    A verificação correta é o pipeline, não o corte de linhas."""
    _h, report = rehydrate(load_config(proj))
    assert report.synthetic > 0, "a fixture tem classe; esperava chunk sintético"
    assert report.mismatch == 0


# ── sync ────────────────────────────────────────────────────────────────
def test_sync_sem_mudancas_nao_reindexa(proj: Path) -> None:
    cfg = load_config(proj)
    r = sync(cfg)
    assert r.indexed == 0 and r.chunks == 0
    assert r.unchanged > 0


def test_sync_aplica_delta(proj: Path) -> None:
    cfg = load_config(proj)
    (proj / "extra.md").write_text("# Extra\n\nMais conteudo.\n", encoding="utf-8")
    r = sync(cfg)
    assert r.indexed == 1 and r.chunks > 0


def test_sync_funciona_sem_git(proj: Path) -> None:
    r = sync(load_config(proj))
    assert r.mode == "hash"


def test_sync_usa_git_quando_disponivel(tmp_path: Path) -> None:
    root = _make(tmp_path)
    if subprocess.run(["git", "init", "-q"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root, capture_output=True,
    )
    cfg = load_config(root)
    index_project(cfg)
    first = sync(cfg)
    assert first.to_commit
    second = sync(cfg)
    assert second.mode == "git" and second.from_commit == first.to_commit


def test_sync_regenera_dicionario(proj: Path) -> None:
    cfg = load_config(proj)
    sync(cfg)
    assert (proj / "knowledge" / "dictionary.json").is_file()


def test_sync_reconstroi_apos_apagar_o_banco(proj: Path) -> None:
    """`.ragx/` é descartável: knowledge/ + working tree bastam."""
    import shutil

    cfg = load_config(proj)
    antes = status(cfg)["chunks"]
    shutil.rmtree(cfg.state_dir)
    sync(cfg)
    assert status(cfg)["chunks"] == antes


def test_knowledge_nao_e_indexado(proj: Path) -> None:
    """Indexar os próprios artefatos criaria um laço de realimentação."""
    cfg = load_config(proj)
    sync(cfg)
    n1 = status(cfg)["documents"]
    sync(cfg)
    assert status(cfg)["documents"] == n1, "knowledge/ está sendo reindexado"


def test_sync_reconstroi_grafo_antes_do_dicionario(proj: Path) -> None:
    """Regressão: o dicionário saía VAZIO porque `sync` o regenerava sem
    reconstruir o grafo antes — e `technologies`/`services` derivam de entidades.

    Encontrado conectando um cliente MCP real: `get_dictionary` devolvia 0
    tecnologias, e ele é a primeira ferramenta que o agente chama.
    """
    import json
    import sqlite3

    cfg = load_config(proj)
    conn = sqlite3.connect(cfg.db_path)
    conn.execute("DELETE FROM entities")
    conn.commit()
    conn.close()

    r = sync(cfg)
    assert r.entities > 0, "sync precisa reconstruir o grafo"

    data = json.loads((proj / "knowledge" / "dictionary.json").read_text(encoding="utf-8"))
    assert data["services"], "dicionário sem serviços: o agente fica sem orientação"
    assert not any("sem tecnologias nem serviços" in w for w in r.warnings)


def test_sync_regenera_fatia_de_federacao(proj: Path) -> None:
    cfg = load_config(proj)
    sync(cfg)
    assert (proj / "knowledge" / "federation" / "service.json").is_file()
