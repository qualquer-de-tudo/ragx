# AGENTS.md — trabalhar NO RAGX

Onboarding técnico para quem vai alterar este repositório: pessoa ou agente.

Não confunda os dois papéis. Este arquivo é sobre **desenvolver o RAGX**. Usar
o RAGX como servidor MCP em outro projeto é [docs/09-mcp.md](docs/09-mcp.md).

> **Leia [docs/02-seguranca.md](docs/02-seguranca.md) antes de escrever
> código.** A promessa central do projeto é que segredo não entra na base. Ela
> é fácil de quebrar sem perceber e cara quando quebra.

---

## 1. O que o RAGX é

Knowledge Engine local. Indexa um repositório, bloqueia segredos na entrada,
responde busca híbrida, monta contexto dentro de um orçamento de tokens e
serve agentes por MCP. Sem servidor, sem nuvem, sem chave de API.

```text
repositório → [Security Gate] → parser → chunks → SQLite → busca/grafo/contexto → MCP → agente
```

Quatro princípios que decidem discussões de desenho:

1. **Nenhum segredo entra na base.** O gate roda *antes* do parser, não depois
   do índice. O que ele bloqueia não existe no banco — então não há ferramenta,
   consulta nem agente que o alcance.
2. **O conhecimento versionado não estoura o Git.** Conteúdo de chunk não é
   versionado (é reidratado do working tree); embeddings vão em int8@256.
3. **MCP é casca fina.** Zero lógica de negócio, zero filesystem — garantido
   por teste arquitetural, não por combinado.
4. **Determinismo.** Mesmo input + mesma versão do chunker = mesmos IDs, em
   qualquer sistema operacional. É por isso que o CI roda nos três.

---

## 2. Estrutura

```text
src/ragx/
  cli/            # Typer. `commands/` tem um módulo por grupo de comando
  security/       # gate, scanner, ignore engine, redactor  ← leia primeiro
  indexing/       # walker, parsers, chunkers, pipeline
  search/         # keyword (FTS5), semântica, híbrida, ranking
  graph/          # entidades, relações, travessia, extratores
  context/        # engine, budget, dedup, compressão, render
  dictionary/     # Knowledge Dictionary
  mcp/            # servidor MCP + operações + orquestração  ← casca fina
  tasks/          # análise, plano, DAG, lease, worker
  federation/     # hub multiprojeto, superfície pública
  storage/        # SQLite, migrações, repositórios, vetores
  base/           # conhecimento base compartilhado (@base/...)

vscode-plugin/    # extensão do VS Code (TypeScript + React no webview)
docs/             # documentação numerada + ADRs
tests/            # unit / integration / security / e2e
install/          # instaladores Linux-macOS (sh) e Windows (ps1)
```

Onde as coisas de verdade acontecem:

| Se você mexe em… | Comece por |
|---|---|
| bloqueio de segredo | `src/ragx/security/gate.py`, `rules/*.yaml` |
| o que entra no índice | `src/ragx/indexing/pipeline.py`, `src/ragx/walk.py` |
| resultado de busca | `src/ragx/search/service.py`, `ranking.py` |
| grafo | `src/ragx/graph/store.py`, `traversal.py` |
| ferramenta MCP | `src/ragx/mcp/server.py` (registro), `tools.py` (contratos) |
| a extensão | `vscode-plugin/src/extension.ts`, `src/rag/McpClient.ts` |

---

## 3. Comandos

```bash
uv sync --all-extras --dev          # ambiente

uv run pytest -q                    # a suíte inteira
uv run pytest tests/security -q     # BLOQUEANTE — nunca aceite vermelho aqui
uv run pytest -m unit -q            # ciclo rápido
uv run ruff check .                 # lint (o CI roda exatamente isto)
uv run ruff check --fix .
uv run mypy src/ragx                # strict em core/ e security/
```

Na extensão:

```bash
cd vscode-plugin
npm ci
npm run typecheck                   # tsc do host E do webview
npm test                            # vitest
npm run build
node scripts/bench-connect.mjs --cmd ragx --cwd /caminho/do/projeto -n 5
```

Marcadores do pytest: `unit`, `integration`, `security`, `e2e`, `slow`.

---

## 4. Como validar uma alteração

Antes de dizer que terminou:

1. `uv run ruff check .` — limpo.
2. `uv run pytest -q` — verde. **Nenhum teste novo pulado ou `xfail`.**
3. `uv run pytest tests/security -q` isolado — a suíte de segurança não pode
   depender de ordem nem de estado deixado por outro teste.
4. Mexeu na extensão? `npm run typecheck && npm test` também.
5. Mexeu em desempenho? **meça antes e depois** e ponha os dois números na
   descrição. "Parece mais rápido" não é resultado.
6. Atualize o [CHANGELOG](CHANGELOG.md) **na mesma alteração**. Não é etapa
   posterior: CHANGELOG escrito depois é CHANGELOG escrito errado.

A suíte se isola sozinha do `$HOME` da máquina (`tests/conftest.py`). Se um
teste seu precisa do hub ou da configuração de usuário, use um `tmp_path` —
teste que lê o `$HOME` real passa na sua máquina e falha na de outra pessoa.

---

## 5. Segurança — as regras que não se negociam

- **Nunca** contorne o `SecurityGate.admit()`. Ele é o único ponto por onde
  conteúdo entra. Se você precisou de outro caminho, o desenho está errado.
- **Nunca** afrouxe uma regra de deny para resolver um falso positivo sem
  compensar na fase 2. Foi assim que `filename-deny:tokens` foi corrigido:
  arquivo de código-fonte deixou de ser bloqueado pelo NOME, mas o conteúdo
  continua passando pela varredura inteira. Ver `tests/security/test_filename_deny.py`.
- **Nunca** adicione `os`, `subprocess`, `pathlib`, `socket` ou cliente HTTP a
  `src/ragx/mcp/`. Existe teste arquitetural que falha
  (`tests/security/test_architecture.py`).
- Não registre em log conteúdo de chunk, valor de segredo, token ou caminho
  absoluto do usuário.
- Caminho vindo de fora (MCP, extensão) é **chave de consulta**, nunca caminho
  de arquivo. Passe por `validate_path()`.
- Mexeu em regra de segurança? Rode `ragx security scan .` neste repositório e
  confira o diff do que passou a ser bloqueado ou liberado.

---

## 6. MCP

O servidor sobe com `ragx mcp serve` (stdio). As ferramentas são registradas em
`build_server()`, em `src/ragx/mcp/server.py`.

Ao adicionar uma ferramenta:

1. Registre em `build_server()` com `@server.tool(description=...)`. A
   descrição é o que o agente lê para decidir se chama — escreva para ele.
2. Envolva em `_guarded(...)`: falha vira erro estruturado, não exceção crua.
3. Valide entrada com um contrato pydantic de `mcp/tools.py`.
4. Passe a resposta por `cap()` — resposta grande é **recusada com orientação**,
   nunca truncada em silêncio.
5. **Documente em [docs/09-mcp.md](docs/09-mcp.md)**, na tabela certa. Há teste
   que compara as ferramentas registradas com as documentadas, nos dois
   sentidos (`tests/unit/test_documentacao_mcp.py`).
6. É escrita? Ela continua listada em `--read-only` e responde
   `write_disabled`. Ferramenta ausente faz o agente inventar um contorno;
   ferramenta que recusa diz a verdade.

`ragx mcp tools --json` mostra o que está exposto agora.

---

## 7. Extensão do VS Code

A extensão **não toca no banco**. Ela fala com o RAGX por MCP (processo quente)
ou pela CLI (um processo por consulta). Lógica de conhecimento fica no Python.

O que importa saber antes de mexer:

- **A conexão custa ~1,6 s**, quase tudo boot do Python e import do SDK de MCP
  — medido, não estimado (`scripts/bench-connect.mjs`). O transporte e o
  handshake somam poucos milissegundos. Portanto: o caminho para ganhar tempo
  **não** é mexer em timeout, é não pagar esse custo duas vezes.
- `conectar()` tem fila (`conexaoEmCurso`). Duas chamadas simultâneas — coisa
  normal entre ativação, troca de pasta e mudança de configuração — subiriam
  **dois** processos Python, e um ficaria órfão.
- Queda do processo dispara `onCrash` e uma reconexão com espera crescente
  (1 s → 60 s, seis tentativas). Sem isso, um RAGX não instalado vira laço de
  `spawn` a 100% de CPU.
- **Contrato do grafo**: o servidor manda a aresta orientada (`src`/`dst`) *e*
  o nó do outro lado (`other`/`other_type`). A tradução mora em `toEdge()`, em
  `src/rag/parse.ts`, com teste de contrato dos dois lados. Ler `other` como se
  fosse `target` foi o que deixou o grafo sem nenhuma aresta.
- A extensão chama a CLI montando argv como texto. `tests/unit/test_plugin_contrato.py`
  confere que todo comando e flag que ela usa existem de verdade.

---

## 8. Padrões de código

- Python ≥ 3.11, `from __future__ import annotations` em todo módulo.
- `ruff` com linha de 100. `mypy --strict` em `ragx.core` e `ragx.security`.
- **Imports pesados vão dentro da função.** `src/ragx/cli/main.py` importa os
  21 módulos de comando só para registrá-los; se cada um puxar seu subsistema
  no topo, `ragx --version` carrega numpy. Já custou ~500 ms em *toda*
  invocação da CLI — inclusive a do servidor MCP.
- Mensagem de erro diz **o que fazer**, não só o que falhou. Compare:
  `"ValidationError"` × `"limit deve ser ≤ 50 (recebido: 500)"`.
- Comentário explica **por quê**, não o quê. Vários comentários deste
  repositório registram um bug real; não os apague ao refatorar em volta.
- Nomes e documentação em português; identificadores de API pública e campos
  de JSON em inglês.

---

## 9. Regras para agentes de IA

- **Meça antes de otimizar.** Este repositório tem baseline: use
  `vscode-plugin/scripts/bench-connect.mjs` e `python -X importtime`. Não
  aceite "deve ficar mais rápido".
- **Não afrouxe teste para ficar verde.** Um teste vermelho está dizendo algo.
  Se ele está errado, conserte o teste e explique por quê na descrição.
- **Não apague comentário que explica um bug antigo.** Ele é a única memória
  de por que o código é assim.
- **Não reverta correção que você não entendeu.** Procure o teste que a cobre
  antes de mexer.
- **Verifique a documentação contra o código.** Ela já esteve errada:
  `docs/09-mcp.md` documentava 20 de 33 ferramentas, e o README prometia uma
  licença que não existia no repositório.
- Ao concluir, diga **o que não foi feito** e por quê. Escopo reduzido em
  silêncio é pior do que escopo não entregue.

---

## 10. Documentação

| Documento | Quando ler |
|---|---|
| [docs/README.md](docs/README.md) | índice |
| [docs/00-visao-geral.md](docs/00-visao-geral.md) | começo |
| [docs/01-arquitetura.md](docs/01-arquitetura.md) | camadas e fluxos |
| [docs/02-seguranca.md](docs/02-seguranca.md) | **antes de escrever código** |
| [docs/06-grafo.md](docs/06-grafo.md) | contrato do grafo |
| [docs/09-mcp.md](docs/09-mcp.md) | ferramentas MCP |
| [docs/13-testes-hardening.md](docs/13-testes-hardening.md) | pirâmide de testes |
| [docs/14-cli.md](docs/14-cli.md) | referência de comandos |
| [docs/adr/](docs/adr/) | por que as decisões são o que são |
| [SECURITY.md](SECURITY.md) | reportar vulnerabilidade |

As ADRs valem mais do que parecem: quase toda discussão de desenho que volta já
foi decidida em uma delas.
