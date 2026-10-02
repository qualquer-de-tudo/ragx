from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing import lock
from ragx.indexing.pipeline import index_project
from ragx.indexing.status_file import STATUS_NAME, write_status

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo-id"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _read(root: Path) -> dict:
    return json.loads((root / ".ragx" / STATUS_NAME).read_text(encoding="utf-8"))


def test_indexar_grava_o_status(proj: Path) -> None:
    index_project(load_config(proj), source="panel")
    st = _read(proj)
    assert st["schema_version"] == 1
    assert st["project"] == {
        "id": "demo-id",
        "name": "demo",
        "root": load_config(proj).root.as_posix(),
    }
    assert st["index"]["source"] == "panel"
    assert st["index"]["mode"] == "incremental"
    assert st["index"]["finished_at"]
    assert st["counts"]["chunks"] > 0
    assert st["counts"]["embeddings"] == st["counts"]["chunks"]
    assert st["counts"]["pending_embeddings"] == 0
    assert st["embedding"]["provider"] == "hashing"
    assert st["running"] is None and st["pending"] is False and st["last_error"] is None


def test_sem_embeddings_conta_pendentes(proj: Path) -> None:
    index_project(load_config(proj), embed=False)
    st = _read(proj)
    assert st["counts"]["embeddings"] == 0
    assert st["counts"]["pending_embeddings"] == st["counts"]["chunks"]


def test_status_mostra_quem_esta_rodando(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    assert lock.try_acquire(cfg.state_dir, "index", "watch")
    try:
        write_status(cfg)
        st = _read(proj)
        assert st["running"]["source"] == "watch"
    finally:
        lock.release(cfg.state_dir)


def test_status_nao_tem_caminho_de_arquivo(proj: Path) -> None:
    index_project(load_config(proj))
    assert "a.py" not in (proj / ".ragx" / STATUS_NAME).read_text(encoding="utf-8")


def test_sem_banco_nao_escreve(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "x"\nid = "x"\n', encoding="utf-8")
    assert write_status(load_config(tmp_path)) is None
    assert not (tmp_path / ".ragx" / STATUS_NAME).exists()


def test_escrita_e_atomica_nao_deixa_temporario(proj: Path) -> None:
    index_project(load_config(proj))
    leftovers = [p.name for p in (proj / ".ragx").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_replace_bloqueado_por_um_leitor_tenta_de_novo_e_grava(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No Windows o painel com o `status.json` aberto faz o `os.replace` falhar por instantes."""
    import os

    index_project(load_config(proj))
    real = os.replace
    falhas = {"n": 0}

    def replace_ocupado(src, dst):
        if falhas["n"] < 2:
            falhas["n"] += 1
            raise PermissionError(13, "arquivo em uso")
        return real(src, dst)

    monkeypatch.setattr("ragx.indexing.status_file.os.replace", replace_ocupado)
    monkeypatch.setattr("ragx.indexing.status_file.time.sleep", lambda s: None)
    assert write_status(load_config(proj)) is not None
    assert falhas["n"] == 2
    assert [p.name for p in (proj / ".ragx").iterdir() if p.name.endswith(".tmp")] == []


def test_replace_que_nunca_libera_nao_deixa_temporario_para_tras(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    index_project(load_config(proj))

    def sempre_ocupado(src, dst):
        raise PermissionError(13, "arquivo em uso")

    monkeypatch.setattr("ragx.indexing.status_file.os.replace", sempre_ocupado)
    monkeypatch.setattr("ragx.indexing.status_file.time.sleep", lambda s: None)
    assert write_status(load_config(proj)) is None  # informativo: nunca derruba a indexação
    assert [p.name for p in (proj / ".ragx").iterdir() if p.name.endswith(".tmp")] == []


def test_running_e_nulo_quando_o_pid_foi_reutilizado(proj: Path) -> None:
    """RAGX-0153: PID vivo, mas o processo que gravou a trava não é o de hoje com esse número."""
    import os

    cfg = load_config(proj)
    index_project(cfg)  # cria o banco
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / lock.LOCK_NAME).write_text(
        json.dumps(
            {"pid": os.getpid(), "op": "index", "source": "watch", "started_at": "x", "proc": "token-de-outra-era"}
        ),
        encoding="utf-8",
    )
    write_status(cfg)
    assert _read(proj)["running"] is None
    # e com o token certo, aparece
    (cfg.state_dir / lock.LOCK_NAME).write_text(
        json.dumps(
            {"pid": os.getpid(), "op": "index", "source": "watch", "started_at": "x", "proc": lock.proc_token(os.getpid())}
        ),
        encoding="utf-8",
    )
    write_status(cfg)
    assert _read(proj)["running"]["source"] == "watch"
