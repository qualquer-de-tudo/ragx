# ADR-0001 — Python 3.11+, uv, Typer, Pydantic

**Status:** aceito · 2026-09-15

## Contexto

O projeto precisa de parsing de código, embeddings, um servidor MCP e uma CLI
usável por dev e por CI. A máquina de desenvolvimento tem Python 3.13.14 e uv 0.5.26
instalados; não há Node nem Go no caminho preferencial do time.

## Decisão

- **Python >= 3.11** como piso (desenvolvimento em 3.13). Justificativa do piso:
  `tomllib` na stdlib (3.11), `StrEnum` (3.11), grupos de exceção e melhorias de
  tipagem. Abaixo de 3.11 exigiria backports que não valem a pena.
- **uv** como gerenciador de dependências e executor de ferramentas; **hatchling**
  como backend de build. Lockfile `uv.lock` versionado.
- **Typer** para a CLI (assinaturas tipadas viram argumentos automaticamente) +
  **Rich** para saída.
- **Pydantic v2** para modelos de fronteira (contratos MCP, manifests, config) e
  **pydantic-settings** para a cascata de configuração.
- No **domínio** (`core/`), `@dataclass(frozen=True, slots=True)` em vez de Pydantic:
  domínio não deve pagar custo de validação em objeto criado milhões de vezes.

## Consequências

Positivas:
- Ecossistema de parsing e ML sem fricção (`tree-sitter`, `tiktoken`, `fastembed`).
- SDK MCP oficial em Python.
- `uv tool install ragx` dá uma instalação isolada e reprodutível.

Negativas:
- Distribuição exige Python no host. Mitigação: publicar no PyPI e documentar
  `uv tool install`; binário único (PyInstaller) fica como item pós-MVP.
- Paralelismo limitado pelo GIL. Mitigação: o gargalo é I/O e chamada de rede;
  `ProcessPoolExecutor` fica disponível para a etapa de parse, que é stateless.

## Alternativas rejeitadas

- **TypeScript/Node** — o indexador anterior (`.index/` neste repositório) é JS.
  Rejeitado porque o ecossistema de parsing de múltiplas linguagens e de embeddings
  locais em Python é claramente superior, e o usuário pediu Python explicitamente.
- **Rust/Go** — desempenho excelente, mas o custo de implementar parsers e clientes
  de embedding não compensa num MVP local-first.
- **Click puro** — funciona, mas Typer entrega o mesmo com tipagem e menos boilerplate.
- **Pydantic em todo o domínio** — custo de validação desnecessário no caminho quente.
