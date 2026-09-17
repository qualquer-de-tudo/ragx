# RAGX

Knowledge Engine local para projetos de software. Indexa um repositório, **protege
segredos por construção**, responde busca híbrida, monta contexto dentro de um
orçamento de tokens e serve tudo a agentes via MCP — sem servidor, sem nuvem.

```text
repositório  →  [Security Gate]  →  conhecimento  →  agentes
```

## Por que existe

Um agente que trabalha num repositório real precisa saber onde fica a
autenticação, quais serviços falam com o Redis, qual o padrão de repositório.
As três saídas usuais são ruins: jogar o repositório inteiro no contexto é caro,
deixar o agente ler arquivos sob demanda faz `.env` vazar para o log e para o
provedor do modelo, e RAG genérico trata código como texto puro.

## Instalação

**Um comando.**

```bash
curl -fsSL https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.ps1 | iex
```

Isso instala a partir do `main`. Para pregar a versão de uma release — e levar
junto a **extensão do VS Code**, que não vem por este caminho — baixe os
arquivos e rode o instalador na pasta deles:

```bash
gh release download v1.0.0-beta.2 --repo qualquer-de-tudo/ragx --dir ragx
cd ragx && bash install.sh                # Windows: .\install.ps1
```

Sem o `gh`, baixe pelo navegador e rode o instalador na pasta — ele encontra o
wheel e o `.vsix` sozinho.

Depois, **abra um terminal novo** (o PATH só vale na próxima sessão):

```bash
ragx --version
```

Passo a passo, comando a comando e opções em [install/](install/README.md).

## Primeiro uso

```bash
ragx init
ragx security scan .        # confira o que será bloqueado ANTES de indexar
ragx index .
ragx search "como funciona autenticação"
```

## O ciclo completo

```bash
ragx index .                              # indexa (incremental)
ragx graph rebuild                        # grafo de entidades e relações
ragx dictionary generate                  # mapa barato do projeto
ragx context "implementar SSO" --tokens 3000
ragx watch                                # o índice acompanha o que você edita
ragx mcp serve                            # 33 ferramentas para o agente
```

Regras compartilhadas entre todos os seus projetos:

```bash
ragx base add https://github.com/renan-s-oliveira/agents
ragx search "guardrails de aprovação"     # responde de @base/agents/...
```

Trabalho grande, do pedido à entrega:

```bash
ragx task analyze "Implementar módulo de assinaturas"
ragx task plan "Implementar módulo de assinaturas" --apply
ragx task next && ragx task context TASK-001
ragx task result TASK-001 --file resultado.json
ragx worker                               # libera as dependentes
```

Colaboração em time:

```bash
git pull && ragx sync                     # reidrata e aplica só o delta
ragx base sync                            # instala o conhecimento base que o projeto exige
ragx export projeto.rag                   # conhecimento portátil
ragx import projeto.rag                   # em outra máquina, sem reindexar
```

Ambiente com vários repositórios (microsserviços):

```bash
ragx federation build                     # publica a superfície pública
ragx project register ../payment-service
ragx project register --from-federation ./contratos/shipping.fed.json
ragx hub sync && ragx hub link
ragx search "criar pagamento" --scope all
```

## Extensão do VS Code

O instalador já a instala, se o `.vsix` estiver na pasta e o `code` no PATH —
por isso o comando único **não** a traz: ele não baixa arquivo nenhum. À mão,
na pasta dos arquivos da release:

```bash
code --install-extension ragx-knowledge-explorer-1.0.0-beta.2.vsix
```

Busca semântica, grafo navegável, dicionário e Context Builder dentro do
editor — do arquivo para o conhecimento e de volta para a linha exata. Não toca
no banco: fala com o RAGX por MCP (processo quente) ou pela CLI. Ver
[vscode-plugin/](vscode-plugin/README.md).

## Princípios

1. **Nenhum segredo entra na base.** O gate roda *antes* do parser, não depois do
   índice. Se o segredo não está no store, nenhuma ferramenta pode servi-lo.
2. **O conhecimento versionado nunca estoura o Git.** 100k chunks cabem em ~42 MB:
   conteúdo de chunk não é versionado (é reidratado do working tree) e os
   embeddings vão em int8@256.
3. **MCP é casca fina.** Zero lógica de negócio, zero acesso a filesystem —
   verificado por teste arquitetural. O agente **controla o índice** (reindexar,
   sincronizar, reconstruir grafo); não controla a máquina.
4. **Determinismo.** Mesmo input + mesma versão do chunker = mesmos IDs, em
   qualquer sistema operacional.

## Documentação

| | |
|---|---|
| [docs/](docs/) | documentação numerada + ADRs |
| [docs/00-visao-geral.md](docs/00-visao-geral.md) | comece aqui |
| [docs/02-seguranca.md](docs/02-seguranca.md) | leia antes de escrever código |
| [docs/14-cli.md](docs/14-cli.md) | referência de comandos |
| [docs/19-watch-e-autonomia-do-agente.md](docs/19-watch-e-autonomia-do-agente.md) | o que o agente pode fazer sozinho |
| [docs/20-task-analyzer.md](docs/20-task-analyzer.md) | executar agora ou documentar antes |
| [docs/09-mcp.md](docs/09-mcp.md) | as ferramentas MCP, uma a uma |
| [AGENTS.md](AGENTS.md) | trabalhar NO RAGX: arquitetura, testes, padrões |
| [SECURITY.md](SECURITY.md) | reportar vulnerabilidade |
| [install/](install/README.md) | instaladores para Linux, macOS e Windows |
| [vscode-plugin/](vscode-plugin/README.md) | extensão do VS Code |
| [task/](task/) | o board completo, fase a fase |

## Estado

MVP completo: 14 fases implementadas, **zero `xfail`** na suíte de segurança
(8 superfícies de vazamento verificadas). Para a contagem de testes de hoje,
`uv run pytest -q` — um número escrito aqui só ficaria desatualizado na
próxima alteração.

**Ressalva importante:** a busca híbrida **não supera o keyword** neste corpus.
Medição real (26 consultas, `fastembed` multilíngue, 1.929 chunks):

```text
keyword      Recall@5 0.77   MRR 0.48   nDCG@10 0.79
semantic     Recall@5 0.62   MRR 0.44   nDCG@10 0.68
hybrid       Recall@5 0.65   MRR 0.49   nDCG@10 0.78
```

O híbrido tem o melhor MRR mas perde em Recall@5 — RRF premia consenso, e o
conjunto de avaliação rotula de menos. Diagnóstico completo com evidência em
[docs/05-busca.md](docs/05-busca.md#avaliação-de-qualidade) e
[`task/fase-02-busca/RAGX-0031-*.md`](task/fase-02-busca/).

Para reproduzir ou medir no seu projeto — **sem precisar de Ollama**:

```bash
uv pip install "ragx[embed]"
ragx config set embedding.provider fastembed
ragx index . --embed-only
ragx eval
```

## Licença

MIT — ver [LICENSE](LICENSE).
