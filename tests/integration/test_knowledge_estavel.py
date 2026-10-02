"""`knowledge/` estável no Git (RAGX-0148): sync sem mudança não suja nada; uma edição toca poucos arquivos."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.dictionary import builder
from ragx.indexing.pipeline import index_project
from ragx.sync.service import sync

pytestmark = pytest.mark.integration


@pytest.fixture()
def cfg(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "ragx.toml").write_text(
        '[project]\nname = "k"\nid = "k"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    for i in range(12):
        (root / f"m{i}.py").write_text(
            f"from m{(i + 1) % 12} import f{(i + 1) % 12}\n\n\ndef f{i}(x):\n    return f{(i + 1) % 12}(x) + {i}\n",
            encoding="utf-8",
        )
    c = load_config(root)
    index_project(c)
    sync(c, full=True)
    return c


def _estado(raiz: Path) -> dict[str, tuple[str, int]]:
    k = raiz / "knowledge"
    return {
        p.relative_to(k).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in k.rglob("*") if p.is_file()
    }


def test_dois_syncs_sem_mudanca_deixam_a_arvore_byte_a_byte_igual_e_o_mtime_intacto(cfg) -> None:
    antes = _estado(cfg.root)
    r = sync(cfg, full=True)
    assert _estado(cfg.root) == antes  # inclusive mtime_ns
    assert r.serialized is not None and r.serialized.files_changed == 0


def test_editar_uma_funcao_toca_poucos_arquivos_e_atualiza_o_generated_at(cfg) -> None:
    import json

    antes = _estado(cfg.root)
    gerado_antes = json.loads((cfg.root / "knowledge" / "manifest.json").read_text(encoding="utf-8"))["generated_at"]
    (cfg.root / "m3.py").write_text((cfg.root / "m3.py").read_text(encoding="utf-8") + "\n\ndef nova():\n    return 1\n", encoding="utf-8")
    index_project(cfg)
    sync(cfg, full=True)
    depois = _estado(cfg.root)
    mudou = [k for k in depois if k not in antes or antes[k][0] != depois[k][0]]
    assert 0 < len(mudou) <= 8, mudou
    gerado_depois = json.loads((cfg.root / "knowledge" / "manifest.json").read_text(encoding="utf-8"))["generated_at"]
    assert gerado_depois != gerado_antes  # o conteúdo mudou: o `generated_at` acompanha


def test_dicionario_gerado_duas_vezes_sem_mudanca_nao_muda_o_arquivo(cfg) -> None:
    p = cfg.root / "knowledge" / "dictionary.json"
    builder.write(cfg, builder.build(cfg)[0])
    antes = (p.read_bytes(), p.stat().st_mtime_ns)
    builder.write(cfg, builder.build(cfg)[0])
    assert (p.read_bytes(), p.stat().st_mtime_ns) == antes


def test_service_json_da_federacao_e_o_manifesto_de_tarefas_ficam_estaveis(cfg) -> None:
    antes = _estado(cfg.root)
    for nome in ("federation/service.json", "tasks/manifest.json"):
        if nome in antes:
            assert _estado(cfg.root)[nome] == antes[nome]
    sync(cfg, full=True)
    depois = _estado(cfg.root)
    for nome in ("federation/service.json", "tasks/manifest.json"):
        assert depois.get(nome) == antes.get(nome)
