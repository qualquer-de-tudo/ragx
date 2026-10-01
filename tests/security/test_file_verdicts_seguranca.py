"""O veredito guardado nunca serve um veredito velho nem deixa nada entrar (RAGX-0139).

O cache só pode manter um arquivo FORA do índice. Cada teste abaixo é uma forma de ele
errar para o lado perigoso: admitir o que o gate bloquearia, ou guardar o segredo.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.secrets_under_test import FIXTURE_ROOT, SECRETS_UNDER_TEST, leaked
from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.storage.db import open_db

pytestmark = pytest.mark.security

TOML = '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'


def _projeto(raiz: Path, extra: str = "") -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "ragx.toml").write_text(TOML + extra, encoding="utf-8")
    (raiz / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    return raiz


def _documentos(cfg) -> set[str]:  # type: ignore[no-untyped-def]
    with open_db(cfg.db_path, read_only=True) as c:
        return {r[0] for r in c.execute("SELECT rel_path FROM documents")}


def _veredito(cfg, rel: str) -> str | None:  # type: ignore[no-untyped-def]
    with open_db(cfg.db_path, read_only=True) as c:
        r = c.execute("SELECT verdict FROM file_verdicts WHERE rel_path = ?", (rel,)).fetchone()
    return r[0] if r else None


def test_bloqueado_fica_fora_do_indice_nas_duas_rodadas(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    shutil.copy(FIXTURE_ROOT / "config.yaml", raiz / "config.yaml")
    (raiz / "dump.txt").write_text(f"senha = {SECRETS_UNDER_TEST[2]}\n", encoding="utf-8")
    cfg = load_config(raiz)
    for _ in range(2):
        index_project(cfg, embed=False)
        assert "config.yaml" not in _documentos(cfg)
    assert _veredito(cfg, "config.yaml") == "blocked"


def test_politica_mais_branda_reavalia_e_entra_redigido_sem_vazar(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    (raiz / "src").mkdir()
    shutil.copy(FIXTURE_ROOT / "src" / "settings.py", raiz / "src" / "settings.py")

    cfg = load_config(raiz)
    index_project(cfg, embed=False)
    assert "src/settings.py" not in _documentos(cfg)  # strict bloqueia
    assert _veredito(cfg, "src/settings.py") == "blocked"

    (raiz / "ragx.toml").write_text(TOML + '\n[security]\npolicy = "balanced"\n', encoding="utf-8")
    cfg = load_config(raiz)
    index_project(cfg, embed=False)
    assert "src/settings.py" in _documentos(cfg)  # o cache NÃO segurou o arquivo fora
    assert _veredito(cfg, "src/settings.py") is None
    with open_db(cfg.db_path, read_only=True) as c:
        conteudo = "\n".join(r[0] for r in c.execute("SELECT content FROM chunks"))
    assert "RAGX:REDACTED" in conteudo
    assert leaked(conteudo) == []  # entrou REDIGIDO, nunca com o valor do segredo


def test_csv_inofensivo_que_ganha_um_segredo_vira_blocked(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    (raiz / "dados.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    cfg = load_config(raiz)
    index_project(cfg, embed=False)
    assert _veredito(cfg, "dados.csv") == "unsupported"

    (raiz / "dados.csv").write_text(
        'a,b\n1,2\naws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n', encoding="utf-8"
    )
    report = index_project(cfg, embed=False)
    assert _veredito(cfg, "dados.csv") == "blocked"
    assert "dados.csv" in report.blocked_paths
    with open_db(cfg.db_path, read_only=True) as c:
        assert c.execute("SELECT 1 FROM security_events WHERE path = 'dados.csv'").fetchone()


def test_nenhum_segredo_chega_ao_banco_nem_a_file_verdicts(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    shutil.copytree(FIXTURE_ROOT, raiz / "fx", dirs_exist_ok=True)
    cfg = load_config(raiz)
    index_project(cfg, embed=False)
    index_project(cfg, embed=False)  # a segunda usa o cache
    with open_db(cfg.db_path, read_only=True) as c:
        colunas = [r[1] for r in c.execute("PRAGMA table_info(file_verdicts)")]
        assert colunas == ["rel_path", "verdict", "rule_id", "size_bytes", "mtime_ns", "checked_at"]
        tudo: list[str] = []
        for tabela in ("chunks", "security_events", "file_verdicts", "documents", "meta"):
            for linha in c.execute(f"SELECT * FROM {tabela}"):
                tudo.extend(str(v) for v in tuple(linha))
    assert leaked("\n".join(tudo)) == []


def test_desativar_regra_invalida_o_cache(tmp_path: Path) -> None:
    raiz = _projeto(tmp_path / "p")
    (raiz / "x.csv").write_text("a\n1\n", encoding="utf-8")
    cfg = load_config(raiz)
    index_project(cfg, embed=False)
    with open_db(cfg.db_path) as c:
        c.execute("UPDATE file_verdicts SET verdict = 'blocked', rule_id = 'falso' WHERE rel_path = 'x.csv'")
        c.commit()
    # com o mesmo contexto o cache vale (prova de que o UPDATE acima é o que o teste usa)
    assert index_project(cfg, embed=False).blocked_paths == ["x.csv"]

    (raiz / "ragx.toml").write_text(TOML + '\n[security]\ndisabled_rules = ["aws-access-key"]\n', encoding="utf-8")
    report = index_project(load_config(raiz), embed=False)
    assert report.blocked_paths == []  # o veredito falso foi descartado e o arquivo reavaliado
    assert _veredito(load_config(raiz), "x.csv") == "unsupported"
