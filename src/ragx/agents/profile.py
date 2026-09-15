"""Perfil de agente — curadoria de conhecimento, NÃO treinamento de modelo.

Não há gradiente, peso ajustado nem fine-tuning. O que se produz é um conjunto
versionável de instruções, regras, skills e exemplos que condiciona o
comportamento de um agente neste projeto. Chamar de "treinar modelo" criaria
expectativa errada sobre custo, tempo e resultado.

Ver docs/10-agent-training.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ragx.config import Config
from ragx.core.errors import UsageError

SCHEMA = 1
AGENTS_DIR = "agents"
GENERATED_SUFFIX = ".generated.md"


class Scope(BaseModel):
    include_paths: list[str] = Field(default_factory=lambda: ["**"])
    exclude_paths: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)  # Fase 11


class KnowledgeStamp(BaseModel):
    index_run: int = 0
    dictionary_hash: str = ""
    chunks: int = 0
    entities: int = 0


class ContextPolicy(BaseModel):
    default_tokens: int = 6000
    graph_depth: int = 2
    prefer: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    schema_version: int = SCHEMA
    name: str
    version: str = "1"
    description: str = ""
    scope: Scope = Field(default_factory=Scope)
    knowledge: KnowledgeStamp = Field(default_factory=KnowledgeStamp)
    context_policy: ContextPolicy = Field(default_factory=ContextPolicy)
    generated_at: str = ""
    generated_by: str = "ragx"


@dataclass
class ProfilePaths:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def instructions(self) -> Path:
        return self.root / "instructions.md"

    @property
    def dictionary(self) -> Path:
        return self.root / "dictionary.json"

    @property
    def rules(self) -> Path:
        return self.root / "rules"

    @property
    def skills(self) -> Path:
        return self.root / "skills"

    @property
    def examples(self) -> Path:
        return self.root / "examples"

    @property
    def proposed(self) -> Path:
        return self.examples / "_proposed"

    @property
    def evaluation(self) -> Path:
        return self.root / "evaluation"


@dataclass
class CreateReport:
    path: str = ""
    created: list[str] = field(default_factory=list)
    template: str = "backend"


TEMPLATES: dict[str, dict[str, Any]] = {
    "backend": {
        "description": "Desenho e implementação de serviços backend neste projeto.",
        "prefer": ["src", "docs/architecture"],
        "rules": {
            "architecture.md": (
                "# Arquitetura\n\n"
                "- Regra de negócio vive no serviço, nunca no controller.\n"
                "- Dependência aponta de fora para dentro.\n"
                "- Toda mudança de contrato público precisa de teste.\n"
            ),
            "coding-standards.md": (
                "# Padrões de código\n\n"
                "- Siga as convenções já detectadas em `dictionary.json`.\n"
                "- Nome de teste descreve o comportamento, não a implementação.\n"
            ),
        },
    },
    "frontend": {
        "description": "Implementação de interface neste projeto.",
        "prefer": ["src", "docs"],
        "rules": {
            "architecture.md": "# Arquitetura\n\n- Componente não conhece a camada de dados.\n",
        },
    },
    "reviewer": {
        "description": "Revisão de código contra os padrões deste projeto.",
        "prefer": ["docs", "src"],
        "rules": {
            "review.md": (
                "# Revisão\n\n"
                "- Aponte defeito de correção antes de estilo.\n"
                "- Cite arquivo e linha em cada apontamento.\n"
            ),
        },
    },
    "docs": {
        "description": "Redação e manutenção da documentação deste projeto.",
        "prefer": ["docs"],
        "rules": {"style.md": "# Estilo\n\n- Português claro, sem jargão desnecessário.\n"},
    },
}

_SECURITY_RULES = """# Regras de segurança

Derivado do ruleset do RAGX. **Este arquivo é obrigatório**: um perfil sem ele
não compila.

## Nunca

- Nunca peça, leia ou reproduza conteúdo de `.env`, `credentials*`, `*.pem`,
  `id_rsa`, `*.key` ou qualquer arquivo bloqueado pelo gate.
- Nunca escreva um segredo em código, log, teste, comentário ou mensagem de commit.
- Nunca desabilite regra de segurança para "fazer passar".
- Nunca envie conteúdo do projeto para serviço externo sem autorização explícita.

## Sempre

- Credencial vem de variável de ambiente, jamais de arquivo versionado.
- Ao encontrar um segredo comitado, PARE e avise — não tente corrigir sozinho.
- Use `ragx security scan .` antes de propor um commit.

## Por quê

O índice do RAGX não contém segredos por construção: o gate roda antes do
parser. Se você acha que precisa de um segredo para completar a tarefa, a
resposta correta é pedir ao humano, não procurar no repositório.
"""

_INSTRUCTIONS = """# {name}

{description}

## Como se orientar neste projeto

Você tem acesso ao conhecimento indexado via MCP. **Não peça "me explique o
projeto"** — isso é caro e impreciso. Em vez disso:

1. `get_dictionary` — tecnologias, serviços, módulos e convenções (barato).
2. `search_hybrid` — localize o que interessa.
3. `build_context` — monte o contexto da tarefa dentro de um orçamento.
4. `get_chunk` — aprofunde em um trecho específico.
{multi}
## Escopo

{scope}

## Regras

{rules}

## Skills disponíveis

{skills}

## O que este projeto usa

{tech}

---

*Perfil gerado por `ragx agent train`. Arquivos em `rules/` e `skills/` editados
à mão são preservados no retreino.*
"""


def create(cfg: Config, name: str, template: str = "backend", scope: str | None = None) -> CreateReport:
    if template not in TEMPLATES:
        raise UsageError(
            f"template desconhecido: {template!r} (use {' | '.join(TEMPLATES)})"
        )
    if not name.replace("-", "").replace("_", "").isalnum():
        raise UsageError(f"nome inválido: {name!r} (use letras, números, - e _)")

    root = cfg.root / AGENTS_DIR / name
    if root.exists():
        raise UsageError(f"perfil já existe: {root}")

    p = ProfilePaths(root)
    report = CreateReport(path=str(root), template=template)
    spec = TEMPLATES[template]

    for folder in (p.rules, p.skills, p.examples, p.proposed, p.evaluation):
        folder.mkdir(parents=True, exist_ok=True)

    manifest = Manifest(
        name=name,
        description=str(spec["description"]),
        scope=Scope(include_paths=[scope] if scope else ["**"]),
        context_policy=ContextPolicy(prefer=list(spec["prefer"])),
    )
    _write(p.manifest, manifest.model_dump_json(indent=2) + "\n")
    report.created.append("manifest.json")

    _write(p.rules / "security.md", _SECURITY_RULES)
    report.created.append("rules/security.md")
    for fname, body in spec["rules"].items():
        _write(p.rules / fname, body)
        report.created.append(f"rules/{fname}")

    _write(
        p.skills / "exemplo.md",
        "---\nname: exemplo\ntriggers: [\"exemplo\"]\n---\n\n"
        "# Skill de exemplo\n\n## Pré-requisitos\n- [ ] ...\n\n"
        "## Passos\n1. ...\n\n## Armadilhas\n- ...\n",
    )
    report.created.append("skills/exemplo.md")

    _write(
        p.evaluation / "cases.yaml",
        "# Avalia RECUPERAÇÃO, não geração — é o que o RAGX controla.\n"
        "- id: eval-001\n"
        '  task: "onde fica a configuração do projeto"\n'
        '  expect_sources: ["ragx.toml"]\n'
        "  must_not_mention: [\"senha\", \"secret\"]\n",
    )
    report.created.append("evaluation/cases.yaml")

    _write(p.instructions, f"# {name}\n\n{spec['description']}\n\n"
           "*Rode `ragx agent train " + name + "` para compilar o conhecimento.*\n")
    report.created.append("instructions.md")
    return report


def load(cfg: Config, name: str) -> tuple[Manifest, ProfilePaths]:
    root = cfg.root / AGENTS_DIR / name
    p = ProfilePaths(root)
    if not p.manifest.is_file():
        raise UsageError(f"perfil não encontrado: {name} (crie com `ragx agent create {name}`)")
    return Manifest(**json.loads(p.manifest.read_text(encoding="utf-8"))), p


def list_profiles(cfg: Config) -> list[str]:
    folder = cfg.root / AGENTS_DIR
    if not folder.is_dir():
        return []
    return sorted(d.name for d in folder.iterdir() if (d / "manifest.json").is_file())


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
