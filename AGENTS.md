# AGENTS.md — trabalhando no próprio RAGX

Este arquivo é para quem (humano ou agente) vai **contribuir com o código do
RAGX**. Se você quer usar o RAGX para indexar *outro* projeto, comece pelo
[README.md](README.md). Se você é um perfil de agente gerado pelo RAGX para
um projeto de terceiros, seu arquivo é `agents/<nome>/instructions.md`, não
este.

## Orientação rápida — não leia o repositório inteiro

O RAGX indexa a si mesmo. Antes de sair lendo arquivo por arquivo:

```bash
ragx index .                                  # se ainda não indexou
ragx search "o que você procura" --mode hybrid
ragx context "sua tarefa" --tokens 3000       # contexto pronto, com fontes
ragx trial                                    # estima, no seu corpus, se o build_context economiza token de verdade
```

Se você é um agente MCP com o servidor `ragx` conectado, use `get_dictionary`,
`search_hybrid` e `build_context` em vez de grep manual — é exatamente o caso
de uso que este projeto existe para resolver, inclusive para si mesmo.

Comece a leitura conceitual por [docs/00-visao-geral.md](docs/00-visao-geral.md)
e [docs/01-arquitetura.md](docs/01-arquitetura.md). O índice completo está em
[docs/README.md](docs/README.md).

## Setup

```bash
uv sync --all-extras --dev
```

Para testar o CLI como usuário final, **não** use `uv tool install` sozinho —
ele copia o pacote para um venv isolado e edições no source não valem até
reinstalar. Use modo editável:

```bash
uv tool install --editable --force --python 3.12 ".[all]"
```

## Testes e lint

```bash
uv run pytest -m "not slow"     # suíte rápida (712 testes)
uv run pytest tests/security    # suíte de segurança isolada — ver marker abaixo
uv run ruff check .
uv run mypy src/ragx/core src/ragx/security   # strict nestes dois pacotes
```

Markers em `pyproject.toml`: `unit`, `integration`, `security` (bloqueante),
`e2e`, `slow` (fora do ciclo rápido). CI roda em `ubuntu-latest`,
`windows-latest` e `macos-latest` — um bug de path ou de encoding que só
aparece numa plataforma é o tipo de coisa que este projeto trata como sério,
não como detalhe.

## A regra que não tem exceção

**Leia [docs/02-seguranca.md](docs/02-seguranca.md) antes de tocar em
qualquer coisa que leia arquivo do projeto do usuário.** O Security Gate roda
*antes* do parser, não depois do índice — é o único componente do sistema sem
atalho permitido, e tem teste arquitetural cobrando isso.

`tests/fixtures/secret_project/` e os `content:aws-*` que aparecem em
`ragx security scan .` dentro deste próprio repositório são segredos **falsos
de propósito** — fixtures do próprio Security Gate. Não são um vazamento real.

## Convenções deste repositório

- Commits: `tipo(escopo): descrição` em português (`fix`, `feat`, `chore`,
  `docs`, `ci`) — ver `git log` para exemplos reais.
- Trabalho planejado vive em [task/](task/), um arquivo por tarefa, com
  `Fora de escopo` explícito. Se a tarefa que você está fazendo crescer além
  do que está escrito lá, isso é sinal para parar e não para improvisar.
- ADRs em [docs/adr/](docs/adr/) registram decisões — o código costuma citar
  o ADR relevante em comentário (ex.: `# CASCA FINA (ADR-0006)`). Leia o ADR
  antes de propor mudar a decisão que ele documenta.
- `knowledge/` é versionado no Git de propósito (conhecimento reidratável,
  ver [docs/12-git-sync.md](docs/12-git-sync.md)) — `ragx graph rebuild` e
  `ragx dictionary generate` alteram arquivos rastreados; isso é esperado,
  não um efeito colateral para reverter.

## CHANGELOG

Toda PR que muda comportamento, corrige bug ou adiciona algo visível ao
usuário final entra em `CHANGELOG.md`, seção `[Não lançado]`, **na mesma PR**
— não depois, não na hora do release. Um changelog escrito de memória dias
depois é o mesmo problema de conhecimento desatualizado que este projeto
existe para resolver, só que aplicado ao próprio processo.

## Onde as coisas ficam desatualizadas

Documentação tem o mesmo risco que qualquer índice: fica velha e continua
respondendo com confiança. Se você notar um número ou uma lista que não bate
com o código (ex.: contagem de ferramentas MCP, estatísticas de indexação),
corrija o documento junto com a mudança de código que causou a divergência —
não deixe para depois.
