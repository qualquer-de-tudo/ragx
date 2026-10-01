"""`verdict_context`: tudo de que o veredito guardado depende (RAGX-0139)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing import verdicts

pytestmark = pytest.mark.unit

BASE = '[project]\nname = "t"\nid = "t"\n'


def _ctx(raiz: Path, extra: str = "") -> str:
    (raiz / "ragx.toml").write_text(BASE + extra, encoding="utf-8")
    return verdicts.verdict_context(load_config(raiz))


def test_estavel_entre_chamadas(tmp_path: Path) -> None:
    assert _ctx(tmp_path) == _ctx(tmp_path)


@pytest.mark.parametrize(
    "extra",
    [
        '\n[security]\npolicy = "balanced"\n',
        "\n[security]\nscan_content = false\n",
        "\n[security]\nmin_entropy = 4.5\n",
        '\n[security]\ndisabled_rules = ["aws-access-key"]\n',
        '\n[index]\nexclude = ["gerado/"]\n',
        '\n[index]\ninclude = ["gerado/"]\n',
        "\n[index]\ninclude_unknown = true\n",
        "\n[index]\nmax_file_bytes = 2048\n",
    ],
)
def test_cada_campo_listado_muda_o_contexto(tmp_path: Path, extra: str) -> None:
    assert _ctx(tmp_path, extra) != _ctx(tmp_path)


def test_ordem_de_disabled_rules_nao_importa(tmp_path: Path) -> None:
    a = _ctx(tmp_path, '\n[security]\ndisabled_rules = ["x", "y"]\n')
    b = _ctx(tmp_path, '\n[security]\ndisabled_rules = ["y", "x"]\n')
    assert a == b


def test_conteudo_de_um_arquivo_de_regras_muda_o_contexto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    antes = _ctx(tmp_path)
    monkeypatch.setattr(verdicts, "_rules_digest", lambda: "outro-hash")
    assert _ctx(tmp_path) != antes


def test_digest_das_regras_cobre_os_tres_arquivos(monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx.security import rules

    lidos: list[str] = []
    original = Path.read_bytes

    def espia(self: Path) -> bytes:
        lidos.append(self.name)
        return original(self)

    verdicts._rules_digest.cache_clear()
    monkeypatch.setattr(Path, "read_bytes", espia)
    verdicts._rules_digest()
    verdicts._rules_digest.cache_clear()
    assert {"patterns.yaml", "filenames.yaml", "default_ignore.txt"} <= set(lidos)
    assert Path(rules.__file__).parent.is_dir()
