"""`EmbeddingCache` em SQLite, em lote (RAGX-0146)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ragx.embeddings.base import EmbeddingCache, pack_f32

pytestmark = pytest.mark.unit


def _vec(seed: int, dim: int = 8) -> np.ndarray:
    return np.random.default_rng(seed).random(dim).astype(np.float32)


def test_ida_e_volta_bit_a_bit(tmp_path: Path) -> None:
    v = _vec(1)
    with EmbeddingCache(tmp_path, "m:1") as c:
        c.put_many([("h1", v)])
        out = c.get_many(["h1", "nao-existe"])
    assert set(out) == {"h1"}
    assert out["h1"].tobytes() == v.tobytes()


def test_get_e_put_sao_involucros_finos(tmp_path: Path) -> None:
    with EmbeddingCache(tmp_path, "m") as c:
        assert c.get("x") is None
        c.put("x", _vec(2))
        assert c.get("x") is not None


def test_janelas_de_500_variaveis(tmp_path: Path) -> None:
    n = 1700  # passa do limite de 999 variáveis do SQLite se não houver janela
    with EmbeddingCache(tmp_path, "m") as c:
        c.put_many([(f"h{i}", _vec(i)) for i in range(n)])
        out = c.get_many([f"h{i}" for i in range(n)])
    assert len(out) == n


def test_um_arquivo_por_modelo_e_nada_por_chunk(tmp_path: Path) -> None:
    with EmbeddingCache(tmp_path, "ollama:nomic/embed") as c:
        c.put_many([(f"h{i}", _vec(i)) for i in range(50)])
    arquivos = [p for p in (tmp_path / "emb").rglob("*") if p.is_file()]
    assert all(p.name.startswith("ollama_nomic_embed.sqlite") for p in arquivos)
    assert not any(p.suffix == ".f32" for p in arquivos)


def test_passagem_do_cache_antigo_importa_e_conta(tmp_path: Path) -> None:
    antigo = tmp_path / "emb" / "m" / "ab"
    antigo.mkdir(parents=True)
    v = _vec(3)
    (antigo / "ab12.f32").write_bytes(pack_f32(v))
    with EmbeddingCache(tmp_path, "m") as c:
        out = c.get_many(["ab12", "zz99"])
        assert c.imported == 1
        assert out["ab12"].tobytes() == v.tobytes()
    # importado: na próxima rodada vem do SQLite, mesmo sem o arquivo antigo
    (antigo / "ab12.f32").unlink()
    with EmbeddingCache(tmp_path, "m") as c:
        assert "ab12" in c.get_many(["ab12"])
        assert c.imported == 0
    assert (tmp_path / "emb" / "m").is_dir()  # a pasta antiga não é apagada


def test_banco_corrompido_e_renomeado_e_recriado(tmp_path: Path) -> None:
    (tmp_path / "emb").mkdir()
    (tmp_path / "emb" / "m.sqlite").write_bytes(b"isto nao e um banco sqlite" * 50)
    with EmbeddingCache(tmp_path, "m") as c:
        c.put_many([("h", _vec(4))])
        assert "h" in c.get_many(["h"])
    assert (tmp_path / "emb" / "m.sqlite.corrupt").is_file()


def test_desligado_nao_cria_nada(tmp_path: Path) -> None:
    with EmbeddingCache(tmp_path, "m", enabled=False) as c:
        c.put_many([("h", _vec(5))])
        assert c.get_many(["h"]) == {}
    assert not (tmp_path / "emb").exists()


def test_erro_de_escrita_vira_sem_cache_e_nao_levanta(tmp_path: Path) -> None:
    with EmbeddingCache(tmp_path, "m") as c:
        assert c._conn is not None
        c._conn.execute("DROP TABLE vecs")  # a escrita passa a falhar com OperationalError
        c.put_many([("h", _vec(6))])  # não levanta
        assert c.get_many(["h"]) == {}


def test_fechado_ao_sair_libera_o_arquivo(tmp_path: Path) -> None:
    with EmbeddingCache(tmp_path, "m") as c:
        c.put_many([("h", _vec(7))])
    (tmp_path / "emb" / "m.sqlite").unlink()  # no Windows falha se a conexão ficou aberta
