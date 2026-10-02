"""Dicionário: resumos extrativos (RAGX-0109), densidade (RAGX-0110) e níveis de leitura (RAGX-0111)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.dictionary import builder
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.tokens import count_tokens

pytestmark = pytest.mark.integration

AUTH = '''"""Autenticação: valida o token no provedor e abre a sessão."""


class AuthService:
    """Autentica usuarios via SSO corporativo.

    Detalhes que não devem entrar no resumo.
    """

    def login(self, c):
        """Valida o token."""
        return self.sso.validate(c)

    def logout(self, sid):
        return self.cache.delete(sid)
'''

# classe SEM docstring própria: cai no docstring do módulo
PAY = '''"""Cobrança no gateway externo."""


class PaymentService:
    def charge(self, order):
        total = order.total
        return self.gateway.charge(total)
'''

# nem a classe nem o módulo dizem nada: o resumo fica nulo, nunca inventado
MUDO = '''class SilentService:
    def run(self, x):
        total = x + 1
        return self.queue.publish(total)
'''

DADOS = '''import enum
from dataclasses import dataclass


class DomainError(Exception):
    """Erro do domínio."""


class Estado(enum.Enum):
    """Estados possíveis."""

    A = 1
    B = 2


@dataclass
class PedidoDTO:
    """Dados de um pedido."""

    id: int
    total: float


class _Interno:
    """Detalhe privado."""

    def a(self):
        return 1

    def b(self):
        return 2
'''

TS = """/**
 * Cliente HTTP do serviço de pedidos.
 */
export class PedidoClient {
  buscar(id: number) {
    return fetch(`/pedidos/${id}`)
  }
  listar() {
    return fetch('/pedidos')
  }
}
"""

README_PKG = "# Pacote billing\n\nCobrança, notas e conciliação financeira do sistema.\n"
INIT_PKG = '"""Pacote de autenticação e sessões."""\n'
DOC_ARQ = "# Arquitetura\n\nO AuthService e o PaymentService formam o núcleo; o SilentService publica na fila.\n"
DOC_AUTH = "# Autenticação\n\nO AuthService valida o token e o PaymentService cobra depois do login.\n"


@pytest.fixture(scope="module")
def proj(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dictn")
    (root / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (root / "src" / "auth").mkdir(parents=True)
    (root / "src" / "billing").mkdir(parents=True)
    (root / "src" / "auth" / "service.py").write_text(AUTH, encoding="utf-8")
    (root / "src" / "auth" / "__init__.py").write_text(INIT_PKG, encoding="utf-8")
    (root / "src" / "billing" / "payment.py").write_text(PAY, encoding="utf-8")
    (root / "src" / "billing" / "README.md").write_text(README_PKG, encoding="utf-8")
    (root / "src" / "billing" / "mudo.py").write_text(MUDO, encoding="utf-8")
    (root / "src" / "dados.py").write_text(DADOS, encoding="utf-8")
    (root / "src" / "cliente.ts").write_text(TS, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "01-arquitetura.md").write_text(DOC_ARQ, encoding="utf-8")
    (root / "docs" / "02-autenticacao.md").write_text(DOC_AUTH, encoding="utf-8")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    return root


def _build(proj: Path) -> dict:
    return builder.build(load_config(proj))[0]


def _servicos(proj: Path) -> dict[str, dict]:
    return {s["name"]: s for s in _build(proj)["services"]}


# ── 0109: resumo extrativo, sem LLM ─────────────────────────────────────
def test_resumo_vem_da_primeira_linha_do_docstring_da_classe(proj: Path) -> None:
    assert _servicos(proj)["AuthService"]["summary"] == "Autentica usuarios via SSO corporativo"


def test_sem_docstring_de_classe_cai_no_docstring_do_modulo(proj: Path) -> None:
    assert _servicos(proj)["PaymentService"]["summary"] == "Cobrança no gateway externo"


def test_ausencia_de_docstring_nao_produz_resumo_inventado(proj: Path) -> None:
    assert "SilentService" in _servicos(proj)
    assert _servicos(proj)["SilentService"]["summary"] is None


def test_bloco_de_documentacao_de_classe_typescript_vira_resumo() -> None:
    """TS/JS/PHP ainda caem em `TextParser` (sem entidade de classe, RAGX-0114): o extrator já sabe ler o bloco."""
    assert builder._resumo_de_classe(TS, builder._fatos_da_classe(TS)) == "Cliente HTTP do serviço de pedidos"


def test_modulo_ganha_resumo_do_readme_ou_do_init(proj: Path) -> None:
    modulos = {m["name"]: m for m in _build(proj)["modules"]}
    assert modulos["src/billing"]["summary"] == "Cobrança, notas e conciliação financeira do sistema"
    assert modulos["src/auth"]["summary"] == "Pacote de autenticação e sessões"


def test_geracao_continua_deterministica(proj: Path) -> None:
    assert builder.stable_digest(_build(proj)) == builder.stable_digest(_build(proj))


# ── 0110: densidade ─────────────────────────────────────────────────────
def test_excecao_enum_dto_e_privado_nao_sao_servico(proj: Path) -> None:
    nomes = set(_servicos(proj))
    assert not nomes & {"DomainError", "Estado", "PedidoDTO", "_Interno"}


def test_nenhum_simbolo_privado_no_dicionario(proj: Path) -> None:
    data = _build(proj)

    def nomes(no: object) -> list[str]:
        achados: list[str] = []
        if isinstance(no, dict):
            for k, v in no.items():
                if k in ("name", "value") and isinstance(v, str):
                    achados.append(v)
                achados += nomes(v)
        elif isinstance(no, list):
            for v in no:
                achados += nomes(v)
        return achados

    privados = [n for n in nomes(data) if n.startswith("_")]
    assert privados == []
    for lista in data["concepts"].values():
        assert not [n for n in lista if n.startswith("_")]


def test_conceito_e_o_que_um_documento_descreve(proj: Path) -> None:
    conceitos = _build(proj)["concepts"]
    assert conceitos, "a fixture tem dois documentos que citam as mesmas classes"
    for classes in conceitos.values():
        assert len(classes) >= 2  # nunca um conceito de uma classe só
        assert all(not c.startswith("_") for c in classes)


def test_o_dicionario_respeita_o_teto_de_tokens(proj: Path) -> None:
    assert count_tokens(json.dumps(_build(proj), ensure_ascii=False)) <= builder._TOKEN_TARGET


# ── 0111: níveis ────────────────────────────────────────────────────────
def test_nivel_2_e_o_dicionario_completo_como_sempre(proj: Path) -> None:
    data = _build(proj)
    assert builder.at_level(data, 2) is data


def test_cada_nivel_e_superconjunto_do_anterior(proj: Path) -> None:
    data = _build(proj)
    n0, n1, n2 = (builder.at_level(data, n) for n in (0, 1, 2))
    for menor, maior in ((n0, n1), (n1, n2)):
        for secao, itens in menor.items():
            if secao in ("level", "schema_version"):
                continue
            assert secao in maior, f"a seção {secao} sumiu ao aprofundar"
            if isinstance(itens, list):
                assert len(itens) <= len(maior[secao])
                for pequeno, grande in zip(itens, maior[secao], strict=False):
                    if isinstance(pequeno, dict) and isinstance(grande, dict):
                        assert set(pequeno) <= set(grande), (secao, set(pequeno) - set(grande))
                        for campo, valor in pequeno.items():
                            assert grande[campo] == valor
    assert n0["level"] == 0 and n1["level"] == 1


def test_o_nivel_0_cabe_em_1000_tokens_e_o_1_em_2500(proj: Path) -> None:
    data = _build(proj)
    assert count_tokens(json.dumps(builder.at_level(data, 0), ensure_ascii=False)) < 1000
    assert count_tokens(json.dumps(builder.at_level(data, 1), ensure_ascii=False)) < 2500


def test_nivel_desconhecido_e_recusado(proj: Path) -> None:
    with pytest.raises(ValueError, match="nível desconhecido"):
        builder.at_level(_build(proj), 3)


def test_mcp_get_dictionary_com_nivel_e_secao(proj: Path) -> None:
    from ragx.mcp.server import KnowledgeAPI

    api = KnowledgeAPI(load_config(proj))
    completo = api.get_dictionary()
    n0 = api.get_dictionary(level=0)
    assert completo["ok"] and n0["ok"]
    assert "glossary" not in n0["data"]["dictionary"] and n0["data"]["dictionary"]["level"] == 0
    assert "glossary" in completo["data"]["dictionary"] or "stats" in completo["data"]["dictionary"]
    por_secao = api.get_dictionary("services", level=1)["data"]["dictionary"]
    assert list(por_secao) == ["services"]
    assert set(por_secao["services"][0]) <= {"name", "path", "summary"}
    # `section` sem `level` continua sendo a seção completa
    assert "depends_on" in api.get_dictionary("services")["data"]["dictionary"]["services"][0]
    erro = api.get_dictionary(level=7)
    assert erro["ok"] is False and erro["error"]["code"] == "invalid_argument"


# ── 0168: repo map ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def proj_mapa(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dictmap")
    (root / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    corpo = "def {nome}(x):\n    \"\"\"Calcula {nome}.\"\"\"\n    total = 0\n    for k in range(x):\n        total += k\n    return {chamada}\n"
    (root / "src").mkdir()
    (root / "src" / "base.py").write_text(corpo.format(nome="funcao_basica", chamada="total"), encoding="utf-8")
    for i in range(4):
        (root / "src" / f"uso{i}.py").write_text(
            "from base import funcao_basica\n\n\n" + corpo.format(nome=f"usa_basica_{i}", chamada="funcao_basica(total)"),
            encoding="utf-8",
        )
    # a camada `tests/`, `task/` e `knowledge/` também chamam a base: não podem entrar no mapa
    for pasta in ("tests", "task", "knowledge"):
        (root / pasta).mkdir()
        (root / pasta / "x.py").write_text(
            "from base import funcao_basica\n\n\n" + corpo.format(nome=f"chama_{pasta}", chamada="funcao_basica(total)"),
            encoding="utf-8",
        )
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    return root


def test_secao_repo_map_respeita_o_orcamento_e_nao_traz_task_knowledge_nem_testes(proj_mapa: Path) -> None:
    data = _build(proj_mapa)
    mapa = data["repo_map"]
    assert mapa and mapa[0]["path"] == "src/base.py"  # o mais chamado fica em primeiro
    assert not [m["path"] for m in mapa if m["path"].startswith(("task/", "knowledge/", "tests/"))]
    assert all(len(m["symbols"]) <= 3 and m["rank"] > 0 for m in mapa)
    texto = "\n".join(f"{m['path']}: {', '.join(m['symbols'])}" for m in mapa)
    assert count_tokens(texto) <= builder._REPO_MAP_TOKENS


def test_o_mapa_aparece_no_nivel_0_e_o_nivel_0_cabe_em_800_tokens(proj_mapa: Path) -> None:
    n0 = builder.at_level(_build(proj_mapa), 0)
    assert n0["repo_map"] and set(n0["repo_map"][0]) == {"path", "symbols"}
    assert count_tokens(json.dumps(n0, ensure_ascii=False)) <= 800


def test_repo_map_avulso_e_identico_em_duas_execucoes_e_apos_rebuild(proj_mapa: Path) -> None:
    from ragx.graph.rank import repo_map

    cfg = load_config(proj_mapa)
    a = repo_map(cfg, tokens=600)
    assert a == repo_map(cfg, tokens=600)
    rebuild(cfg)  # sem mudança de código
    assert a == repo_map(cfg, tokens=600)
    from ragx.graph.rank import MapEntry, format_line

    assert count_tokens("\n".join(format_line(MapEntry(m["path"], m["rank"], tuple(m["symbols"]))) for m in a)) <= 600


def test_mcp_get_dictionary_nivel_0_inclui_o_mapa(proj_mapa: Path) -> None:
    from ragx.mcp.server import KnowledgeAPI

    out = KnowledgeAPI(load_config(proj_mapa)).get_dictionary(level=0)
    assert out["ok"] and out["data"]["dictionary"]["repo_map"][0]["path"] == "src/base.py"


def test_comando_graph_rank_lista_e_marca_o_que_entra_no_mapa(proj_mapa: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from ragx.cli.main import app

    monkeypatch.chdir(proj_mapa)
    r = CliRunner().invoke(app, ["graph", "rank", "--top", "5"])
    assert r.exit_code == 0 and "src/base.py" in r.output
    j = CliRunner().invoke(app, ["graph", "rank", "--json"])
    assert j.exit_code == 0 and json.loads(j.output)["map"][0]["path"] == "src/base.py"
