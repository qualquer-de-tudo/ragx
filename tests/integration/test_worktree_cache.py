"""Cache de embedding compartilhado entre worktrees (RAGX-0170)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from ragx import gitinfo
from ragx.config import load_config
from ragx.embeddings.base import EmbeddingCache, pack_f32
from ragx.embeddings.hashing import HashingEmbedder
from ragx.indexing.embed import shared_cache_root
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.integration

MODELO = "hashing:64"


def _vec(i: int) -> np.ndarray:
    v = np.zeros(8, dtype=np.float32)
    v[i % 8] = 1.0
    return v


# ── EmbeddingCache com `also_read` ──────────────────────────────────────
def test_cache_le_do_local_e_importa_para_o_compartilhado(tmp_path: Path) -> None:
    local, compartilhado = tmp_path / "local", tmp_path / "comum"
    with EmbeddingCache(local, MODELO) as c:
        c.put_many([("h1", _vec(1)), ("h2", _vec(2))])
    with EmbeddingCache(compartilhado, MODELO, also_read=[local]) as c:
        achados = c.get_many(["h1", "h2", "h3"])
        assert sorted(achados) == ["h1", "h2"] and c.imported_shared == 2
    # o que veio do local agora está no compartilhado: outro worktree o encontra sem tocar no local
    with EmbeddingCache(compartilhado, MODELO) as c:
        assert sorted(c.get_many(["h1", "h2"])) == ["h1", "h2"]


def test_dois_worktrees_se_ajudam_pelo_compartilhado(tmp_path: Path) -> None:
    comum = tmp_path / "comum"
    with EmbeddingCache(comum, MODELO, also_read=[tmp_path / "local-a"]) as a:
        a.put_many([("h1", _vec(1))])
    with EmbeddingCache(comum, MODELO, also_read=[tmp_path / "local-b"]) as b:
        assert list(b.get_many(["h1"])) == ["h1"]
        assert b.imported_shared == 0  # estava no PRÓPRIO compartilhado, não veio de outra raiz


def test_formato_antigo_por_arquivo_em_outra_raiz_tambem_e_lido(tmp_path: Path) -> None:
    local, comum = tmp_path / "local", tmp_path / "comum"
    antigo = local / "emb" / "hashing_64" / "ab"
    antigo.mkdir(parents=True)
    (antigo / "abcdef.f32").write_bytes(pack_f32(_vec(3)))
    with EmbeddingCache(comum, MODELO, also_read=[local]) as c:
        assert list(c.get_many(["abcdef"])) == ["abcdef"] and c.imported_shared == 1


def test_a_propria_raiz_em_also_read_e_ignorada_e_cache_alheio_ilegivel_nao_derruba(tmp_path: Path) -> None:
    comum, alheio = tmp_path / "comum", tmp_path / "alheio"
    (alheio / "emb").mkdir(parents=True)
    (alheio / "emb" / "hashing_64.sqlite").write_bytes(b"isto nao e um banco sqlite")
    with EmbeddingCache(comum, MODELO, also_read=[comum, alheio]) as c:
        assert c.also_read == [alheio / "emb"]
        assert c.get_many(["x"]) == {}


# ── raiz compartilhada e worktrees reais ────────────────────────────────
def _git(cwd: Path, *args: str) -> None:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"git indisponível ou falhou: {r.stderr[:120]}")


def _repo_com_projeto(raiz: Path) -> None:
    raiz.mkdir()
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "w"\nid = "w"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (raiz / ".gitignore").write_text(".ragx/\n", encoding="utf-8")
    for i in range(6):
        (raiz / f"m{i}.py").write_text(
            f'"""Modulo {i}."""\n\n\ndef funcao_{i}(x):\n    """Calcula {i}."""\n    total = 0\n'
            f"    for k in range(x):\n        total += k * {i}\n    return total + {i}\n",
            encoding="utf-8",
        )
    _git(raiz, "init", "-q", "-b", "main")
    _git(raiz, "config", "user.email", "t@t")
    _git(raiz, "config", "user.name", "t")
    _git(raiz, "add", "-A")
    _git(raiz, "commit", "-qm", "c1")


@pytest.fixture
def embeds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Quantos textos o embedder de verdade recebeu, por chamada."""
    chamadas: list[int] = []
    original = HashingEmbedder.embed_documents

    def conta(self, textos):
        chamadas.append(len(textos))
        return original(self, textos)

    monkeypatch.setattr(HashingEmbedder, "embed_documents", conta)
    return chamadas


def test_worktree_novo_nao_reembute_o_que_o_irmao_ja_embutiu(tmp_path: Path, embeds: list[int]) -> None:
    principal = tmp_path / "principal"
    _repo_com_projeto(principal)
    index_project(load_config(principal))
    assert sum(embeds) > 0
    embutidos_no_principal = sum(embeds)
    embeds.clear()

    irmao = tmp_path / "irmao"
    _git(principal, "worktree", "add", "-q", "-b", "outra", str(irmao))
    index_project(load_config(irmao))
    assert sum(embeds) == 0, "o worktree novo reembutiu chunks de conteúdo idêntico ao do irmão"

    comum = gitinfo.common_dir(principal)
    assert comum is not None
    assert shared_cache_root(load_config(irmao)) == shared_cache_root(load_config(principal)) == comum / "ragx" / "cache"
    assert (comum / "ragx" / "cache" / "emb" / "hashing_64.sqlite").is_file()
    assert embutidos_no_principal > 0


def test_chunk_diferente_no_worktree_e_embutido_e_o_resto_vem_do_cache(tmp_path: Path, embeds: list[int]) -> None:
    principal = tmp_path / "principal"
    _repo_com_projeto(principal)
    index_project(load_config(principal))
    embeds.clear()
    irmao = tmp_path / "irmao"
    _git(principal, "worktree", "add", "-q", "-b", "outra", str(irmao))
    alvo = irmao / "m2.py"
    alvo.write_text(alvo.read_text(encoding="utf-8").replace("total += k * 2", "total += k * 99"), encoding="utf-8")
    index_project(load_config(irmao))
    assert 0 < sum(embeds) <= 2  # só o chunk que mudou


def test_o_indice_do_irmao_nao_e_alterado(tmp_path: Path, embeds: list[int]) -> None:
    import sqlite3

    principal = tmp_path / "principal"
    _repo_com_projeto(principal)
    cfg_p = load_config(principal)
    index_project(cfg_p)

    def retrato() -> tuple:
        conn = sqlite3.connect(cfg_p.db_path)
        try:
            return (
                conn.execute("SELECT COUNT(*), MAX(rowid) FROM embeddings").fetchone(),
                conn.execute("SELECT rel_path, content_hash FROM documents ORDER BY rel_path").fetchall(),
            )
        finally:
            conn.close()

    antes = retrato()
    irmao = tmp_path / "irmao"
    _git(principal, "worktree", "add", "-q", "-b", "outra", str(irmao))
    index_project(load_config(irmao))
    assert retrato() == antes


def test_fora_de_git_o_cache_e_o_local_de_sempre(tmp_path: Path, embeds: list[int]) -> None:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "w"\nid = "w"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f(x):\n    total = x\n    total += 1\n    total += 2\n    return total\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert gitinfo.common_dir(tmp_path) is None
    assert shared_cache_root(cfg) == cfg.state_dir / "cache"
    index_project(cfg)
    assert (cfg.state_dir / "cache" / "emb" / "hashing_64.sqlite").is_file()


def test_pasta_comum_sem_permissao_cai_para_o_cache_local(tmp_path: Path, embeds: list[int], monkeypatch: pytest.MonkeyPatch) -> None:
    principal = tmp_path / "principal"
    _repo_com_projeto(principal)
    cfg = load_config(principal)
    comum = gitinfo.common_dir(principal)
    assert comum is not None
    original = EmbeddingCache._connect

    def sem_permissao(self):
        if comum in self.path.parents:
            raise PermissionError("somente leitura")
        return original(self)

    monkeypatch.setattr(EmbeddingCache, "_connect", sem_permissao)
    index_project(cfg)
    assert (cfg.state_dir / "cache" / "emb" / "hashing_64.sqlite").is_file()  # usou o local
    assert not (comum / "ragx").exists()


def test_worktree_status_mostra_chunks_em_comum_e_o_cache(tmp_path: Path, embeds: list[int]) -> None:
    import json

    from typer.testing import CliRunner

    from ragx import worktrees
    from ragx.cli.main import app

    principal = tmp_path / "principal"
    _repo_com_projeto(principal)
    index_project(load_config(principal))
    irmao = tmp_path / "irmao"
    _git(principal, "worktree", "add", "-q", "-b", "outra", str(irmao))
    alvo = irmao / "m2.py"
    alvo.write_text(alvo.read_text(encoding="utf-8").replace("total += k * 2", "total += k * 99"), encoding="utf-8")
    index_project(load_config(irmao))

    rel = worktrees.report(load_config(principal))
    por_ramo = {w["branch"]: w for w in rel["worktrees"]}
    assert por_ramo["main"]["current"] is True and "shared_chunks" not in por_ramo["main"]
    outro = por_ramo["outra"]
    assert outro["indexed"] and outro["chunks"] > 0
    # só o chunk editado difere: quase tudo é comum
    assert 0 < outro["shared_chunks"] < outro["chunks"] and outro["chunks"] - outro["shared_chunks"] <= 2
    assert rel["embedding_cache"]["shared"] is True and rel["embedding_cache"]["size_mb"] >= 0

    r = CliRunner().invoke(app, ["worktree", "status", str(principal), "--json"])
    assert r.exit_code == 0, r.output
    assert {w["branch"] for w in json.loads(r.output)["worktrees"]} == {"main", "outra"}
    r = CliRunner().invoke(app, ["worktree", "status", str(principal)])
    assert r.exit_code == 0 and "em comum com este" in " ".join(r.output.split())


def test_worktree_status_fora_de_git_nao_quebra(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from ragx.cli.main import app

    (tmp_path / "ragx.toml").write_text('[project]\nname = "w"\nid = "w"\n', encoding="utf-8")
    r = CliRunner().invoke(app, ["worktree", "status", str(tmp_path)])
    assert r.exit_code == 0 and "Fora de um repositório git" in " ".join(r.output.split())


def test_pasta_git_comum_sem_subprocesso_bate_com_o_git(tmp_path: Path) -> None:
    from ragx.indexing.embed import _pasta_git_comum

    principal = tmp_path / "principal"
    _repo_com_projeto(principal)
    irmao = tmp_path / "irmao"
    _git(principal, "worktree", "add", "-q", "-b", "outra", str(irmao))
    sub = principal / "pacote" / "interno"
    sub.mkdir(parents=True)  # uma raiz de projeto dentro do repositório
    for raiz in (principal, irmao, sub):
        assert _pasta_git_comum(raiz) == gitinfo.common_dir(raiz) == (principal / ".git").resolve()
    solta = tmp_path / "fora"
    solta.mkdir()
    assert _pasta_git_comum(solta) is None
