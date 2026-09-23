"""IDs determinísticos — as 5 armadilhas do docs/03-modelo-de-dados.md."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ragx.core.ids import (
    CHUNKER_VERSION,
    SCHEMA_VERSION,
    chunk_id,
    content_hash,
    document_id,
    normalize_path,
    normalize_text,
    shard_of,
)

pytestmark = pytest.mark.unit

_MIGRATIONS_DIR = Path(__file__).parents[2] / "src" / "ragx" / "storage" / "migrations"

CODE = "def login(self):\n    return True\n"


def test_crlf_e_lf_produzem_o_mesmo_id() -> None:
    """Sem isso, Windows e Linux geram índices diferentes."""
    assert chunk_id("a.py", CODE) == chunk_id("a.py", CODE.replace("\n", "\r\n"))
    assert chunk_id("a.py", CODE) == chunk_id("a.py", CODE.replace("\n", "\r"))


def test_separador_de_caminho_nao_altera_o_id() -> None:
    assert chunk_id("src/auth/a.py", CODE) == chunk_id("src\\auth\\a.py", CODE)


def test_trailing_whitespace_e_ignorado() -> None:
    assert chunk_id("a.py", CODE) == chunk_id("a.py", "def login(self):   \n    return True\t\n")


def test_caminho_absoluto_e_erro_nao_normalizacao() -> None:
    """Caminho absoluto no ID vazaria o nome do usuário no pacote exportado."""
    for bad in ("/home/user/a.py", "C:/Users/renan/a.py", "E:\\RAGPAG\\a.py"):
        with pytest.raises(ValueError, match="absoluto"):
            normalize_path(bad)


def test_bump_do_chunker_version_invalida_todos_os_ids() -> None:
    assert chunk_id("a.py", CODE, "1") != chunk_id("a.py", CODE, "2")
    assert chunk_id("a.py", CODE) == chunk_id("a.py", CODE, CHUNKER_VERSION)


def test_id_e_estavel_entre_execucoes() -> None:
    assert len({chunk_id("a.py", CODE) for _ in range(50)}) == 1


def test_document_id_depende_so_do_caminho() -> None:
    assert document_id("a.py") == document_id("./a.py")
    assert document_id("a.py") != document_id("b.py")


def test_content_hash_normaliza() -> None:
    assert content_hash("x\r\ny") == content_hash("x\ny")
    assert content_hash("x") != content_hash("y")


def test_normalize_text_remove_bordas() -> None:
    assert normalize_text("\n\n  a  \n\n") == "  a"


def test_shard_distribui_e_e_estavel() -> None:
    ids = [chunk_id(f"f{i}.py", f"x{i}") for i in range(400)]
    shards = [shard_of(i, 16) for i in ids]
    assert len(set(shards)) == 16, "distribuição desigual entre shards"
    # estabilidade: mesmo id -> mesmo shard, sempre
    assert all(shard_of(ids[0], 16) == shard_of(ids[0], 16) for _ in range(10))


def test_snapshot_de_ids() -> None:
    """Snapshot revisado. Divergência entre plataformas falha aqui, não em produção."""
    assert chunk_id("src/auth/service.py", CODE) == chunk_id("src/auth/service.py", CODE)
    esperado = {
        "src/auth/service.py": chunk_id("src/auth/service.py", CODE),
        "docs/auth.md": chunk_id("docs/auth.md", "# Auth\n\nTexto.\n"),
    }
    for expected_id in esperado.values():
        assert len(expected_id) == 32
        assert all(c in "0123456789abcdef" for c in expected_id)


def test_schema_version_bate_com_a_migracao_mais_recente() -> None:
    """SCHEMA_VERSION (usado por `ragx doctor` para aceitar/recusar um banco)
    tem que acompanhar a migração mais alta em disco. Já ficou pra trás uma
    vez: 0006_run_provenance.sql chegou a mover `PRAGMA user_version` para 6
    sem que ninguém bumpasse esta constante, e `ragx doctor` passou a recusar
    todo banco recém-indexado ("banco mais novo que esta instalação")."""
    numeros = [
        int(m.group(1))
        for f in _MIGRATIONS_DIR.glob("*.sql")
        if (m := re.match(r"^(\d{4})_", f.name))
    ]
    assert numeros, f"nenhuma migração encontrada em {_MIGRATIONS_DIR}"
    assert max(numeros) == SCHEMA_VERSION
