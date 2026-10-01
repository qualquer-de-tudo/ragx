# 25 — Spec da v2

Derivada da [auditoria 24](24-auditoria-v2.md) (velocidade, tokens, frescor,
painel) e da [auditoria 23](23-auditoria-e-evolucao-do-rag.md) (qualidade da
recuperação, fase 14). Cada requisito aqui aponta para os achados que o
justificam e para as tarefas em [`task/`](../task/README.md) que o entregam.

## 1. Objetivo

> Um agente que trabalha num repositório real gasta **menos tokens**, **não
> espera** o RAGX e **nunca raciocina sobre código velho** — e a pessoa **vê**
> isso acontecer no painel.

O produto existe para três promessas. A v1 as declara; a v2 as **mede, cumpre e
prova**:

| Promessa | Como a v2 a cumpre | Como a v2 a prova |
|---|---|---|
| **Economizar tokens** | Respostas sem duplicação e compactas; conjunto mínimo de ferramentas; dedupe de sessão; hierarquia mapa → resumo → trecho | Telemetria com o tamanho **real** entregue; baseline honesto; A/B com e sem o RAGX |
| **Não deixar o Claude lento** | Poda correta, embedder aquecido, hooks leves, caches com invalidação certa | SLOs medidos no CI (seção 3) |
| **Sempre atualizado** | Edição não commitada entra em segundos; `refresh` incremental de verdade; cache que não serve resultado velho | `stale` explícito no resultado e latência edição→busca medida |

## 2. Princípios (não mudam)

1. **O Security Gate roda antes do parser.** Nenhuma tarefa da v2 o enfraquece,
   o contorna ou o move. Tarefas que tocam o caminho de leitura de arquivo
   (poda de diretórios, frescor na consulta, hooks de edição) **precisam** de
   teste em `tests/security` provando que nenhum segredo novo entra.
2. **MCP é casca fina**: zero lógica de negócio e zero acesso a filesystem no
   servidor, verificado por teste arquitetural. Os formatos compactos e o
   dedupe de sessão vivem na camada de serviço, não no servidor.
3. **Determinismo**: mesma entrada e mesma versão, mesmos IDs, em qualquer
   sistema. Mudança de formato de resposta é versionada.
4. **Medir antes e depois.** Toda tarefa de desempenho ou de tokens registra o
   número antes e depois no CHANGELOG. Sem medição, não está pronta.
5. **Local-first, sem nuvem.** Nada na v2 exige rede, chave de API ou LLM para
   funcionar. Modelos opcionais (rerank, embedding de código) ficam atrás de
   flag e desligados por padrão até haver ganho medido.

## 3. SLOs da v2 (critérios de saída)

Medidos no corpus do próprio repositório (≈6,6k chunks) numa máquina de
desenvolvimento. O que é **medido hoje** vem da auditoria 24; a meta é o que a
v2 precisa atingir.

| # | Métrica | Hoje | Meta v2 | Achados |
|---|---|---:|---:|---|
| S1 | Tokens no fio de `build_context` com `tokens=3000` | 7.684 | **≤ 3.200** (dentro de 8% do pedido) | C-01, M-03 |
| S2 | Custo fixo de ferramentas MCP por sessão (nome+descrição+schema) | 2.660 | **≤ 600** | M-04, M-11 |
| S3 | `get_dictionary` nível 0 | 8.660 | **≤ 800** | fase 14 (0111) |
| S4 | Indexação sem mudança, repo de ~20k arquivos | 7,6–15 s | **≤ 1,5 s** | M-01, M-07 |
| S5 | `refresh` incremental, 1–4 arquivos | 26–91 s | **≤ 3 s** | M-02 |
| S6 | Latência edição→visível na busca (arquivo não commitado) | indefinida (manual) | **≤ 5 s** | M-10 |
| S7 | `ragx claude hint` (SessionStart) | 481–659 ms | **≤ 120 ms** | M-08 |
| S8 | Bloqueio síncrono de `git commit` pelo hook | 539–1041 ms | **≤ 150 ms** | M-09 |
| S9 | 1ª `search_hybrid` do processo | 3,0–5,0 s | **≤ 600 ms percebidos** (aquecimento em segundo plano) | M-06 |
| S10 | `search_hybrid` quente | 104–172 ms | **≤ 60 ms** | C-02 |
| S11 | Painel: processos filhos por minuto com 12 projetos, janela visível / minimizada | ≈290+ / ≈290+ | **≤ 20 / 0** | U-02, U-03, U-04 |
| S12 | Cache do `build_context` | serve resultado de outro filtro | **0 acertos incorretos** em teste de propriedade | C-04 |
| S13 | Adoção: sessões em projeto indexado que chamam o RAGX | 8% (3 de 38) | **medida e visível no painel**; meta a fixar depois de 2 semanas de dados | M-05, M-12 |
| S14 | Economia real contra baseline de Grep | desconhecida | **medida por A/B** e publicada | M-03 |

S13 e S14 são de **medição**, não de valor-alvo: a v2 não promete um número que
ainda não sabe qual é.

## 4. Escopo

### 4.1 Dentro

**Fase 19 — Velocidade e frescor** (caminho quente e escrita): poda de
diretórios, embedder preguiçoso e aquecido, `refresh` leve, `load_index`
vetorizado e cacheado, cache do `build_context` correto, `replace_for_document`
por diff, modelo do índice contra configurado, `scope` do MCP, hooks leves,
frescor de edições não commitadas, expansão do grafo.

**Fase 20 — Economia de tokens**: um só formato de contexto, compactação das
respostas, conjunto mínimo de ferramentas, dedupe de sessão, `instructions` e
descrições para Tool Search, adoção (hook que lembra do índice, subagente
explorador), telemetria honesta e A/B de economia.

**Fase 21 — Recuperação v2**: herda as 14 tarefas pendentes da fase 14 e
acrescenta prefixo contextual determinístico, repo map compacto, conjunto-ouro
do git e índice por worktree/branch.

**Fase 22 — Painel v2**: desempenho (pausar pollers, `git` sem spawn, conexões
baratas, telemetria incremental, re-render, remoção do fallback `sql.js`),
fundação de design (tokens, primitivos, contraste, responsividade), feedback e
estados (toasts, skeletons, atalhos, paleta) e produto (economia em moeda,
preview de contexto, linha do tempo de sessões, saúde do índice, bandeja,
auto-update, tema claro).

### 4.2 Fora de escopo (decidido; não reabrir sem motivo novo)

- Substituir NumPy por `sqlite-vec` ou ANN (auditoria 24, 7.3).
- LSP/Serena ou SCIP como núcleo do grafo.
- Code execution com MCP (sandbox).
- ColBERT, SPLADE, late chunking.
- LLMLingua/TOON generalizado; contextual retrieval com LLM.
- Modelos de embedding de 7B ou mais.
- Bloquear `Grep`/`Read` por hook (só sugerir).
- Mostrar a consulta do agente no painel (o log não a tem, de propósito).
- i18n do painel (só PT-BR até haver público fora do Brasil).
- Assinatura de código do `.exe` (RAGX-0124, adiada); o auto-update da fase 22
  é entregue **com a ressalva** de que depende dela para ser confortável.
- Linux e macOS do painel (fase 17).

## 5. Requisitos por área

Os IDs (`C-`, `M-`, `I-`, `U-`) apontam para a auditoria 24.

### 5.1 Velocidade e frescor — fase 19

- **R-V1** A poda de diretórios segue a regra do git: uma negação só impede a
  poda do diretório que a contém ou de um pai dele, nunca de irmãos nem de
  filhos de um diretório ignorado (M-01).
- **R-V2** O indexador não carrega o modelo de embedding quando não há chunk
  pendente (M-07).
- **R-V3** `refresh` por MCP é **incremental** por padrão e não regrava
  `knowledge/`; o `sync` completo só por pedido explícito (M-02).
- **R-V4** `load_index` é vetorizado e cacheado por processo, invalidado por um
  contador de geração gravado em `meta`, não por `mtime` (C-02).
- **R-V5** A chave do cache do `build_context` inclui filtros e a configuração
  que altera o resultado, só considera runs **terminados**, tem despejo e grava
  de forma atômica (C-04).
- **R-V6** `replace_for_document` preserva por diff de id o que não mudou:
  embeddings e pontes entidade→chunk sobrevivem a uma edição (C-06).
- **R-V7** A busca usa o modelo **configurado**; sem vetores desse modelo,
  devolve o motivo em `degraded` em vez de falhar ou responder ao acaso (C-07).
- **R-V8** `scope` é honrado ou recusado com erro explícito; nunca ignorado em
  silêncio (C-05).
- **R-V9** O embedder e o contador de tokens são aquecidos em segundo plano
  após o `initialize` do servidor MCP (M-06, C-08).
- **R-V10** `claude hint` e `hook-run` têm um ponto de entrada que não importa
  a CLI inteira; o hook de git faz a checagem barata antes de subir Python
  (M-08, M-09).
- **R-V11** Edição não commitada entra no índice por dois caminhos baratos:
  verificação de `stat` dos arquivos dos top-K na consulta e um hook
  `PostToolUse` assíncrono (M-10). O resultado carrega `stale` quando o disco
  está à frente do índice.
- **R-V12** A expansão do grafo semeia a partir do topo da busca, respeita os
  filtros e calcula grau só dos nós visitados (C-03).
- **R-V13** `ragx context` sem `--tokens` usa o padrão da configuração (C-11).

### 5.2 Economia de tokens — fase 20

- **R-T1** `build_context` devolve **uma** representação do conteúdo, compacta
  e sem indentação; o orçamento e `estimated_tokens` contam o que de fato sai,
  incluindo o cabeçalho dos fragmentos (C-01, M-03).
- **R-T2** Todas as respostas MCP usam serialização compacta; `_hit` deixa de
  repetir `project`, encurta o id e arredonda o score; `outputSchema` e
  `structuredContent` saem quando não servem ao modelo (M-11).
- **R-T3** O servidor MCP expõe um conjunto **mínimo** de ferramentas
  (alvo: 6) com schemas enxutos; as de administração ficam na CLI e as de
  tarefa atrás de flag (M-04).
- **R-T4** O servidor entrega `instructions` ≤ 2 KB e a lista de ferramentas é
  **estável** durante a sessão (não invalida o cache de prompt).
- **R-T5** Dedupe de sessão: um chunk já entregue na sessão volta como
  referência curta, não como conteúdo.
- **R-T6** A telemetria registra `ok`, `err_code`, `resp_chars` e tokens
  **reais** em toda chamada, e o baseline passa a ter definição honesta
  (M-12, M-03).
- **R-T7** Adoção: um hook `PreToolUse` em `Grep|Glob` lembra **uma vez por
  sessão** do índice, sem bloquear; o subagente `ragx-explorer` é instalável
  (M-05).
- **R-T8** A economia é **medida por A/B** (`claude -p` com e sem o MCP sobre
  tarefas do próprio git) e o número publicado traz o método (S14).

### 5.3 Recuperação — fase 21

As 14 tarefas pendentes da fase 14 (0099, 0101, 0103–0114) são pré-requisito de
qualidade e seguem como estão. A fase 21 acrescenta o que a pesquisa trouxe:
prefixo contextual determinístico, repo map compacto (nível 0 do dicionário e
do SessionStart), conjunto-ouro derivado do git e índice por worktree/branch.

### 5.4 Painel — fase 22

- **R-P1** O painel não gasta CPU quando não está à vista: snapshot e conexões
  pausam com a janela minimizada ou escondida e atualizam ao voltar (U-04).
- **R-P2** O snapshot não cria processos `git`: lê `.git/HEAD` e as refs, com
  cache por `mtime`, e usa o `git` só como último recurso (U-02).
- **R-P3** A checagem de conexões é barata: versão do `ragx` cacheada pelo
  `mtime` do executável, `docker ps` em vez de `docker info`, ping HTTP antes
  do Docker, intervalo maior em segundo plano (U-03).
- **R-P4** A telemetria é incremental (offset por arquivo, buckets diários) e o
  log da CLI rotaciona (U-01).
- **R-P5** Só re-renderiza o que mudou: o snapshot só é enviado se mudou, as
  referências inalteradas são preservadas e os cards são memoizados (U-05).
- **R-P6** O fallback que lê `knowledge.db` inteiro some; sem `status.json` o
  painel diz "reindexe" (U-06). Isso remove a dependência de `sql.js`.
- **R-P7** Tokens de design completos (espaço, tipografia, elevação, estado
  semântico), contraste AA e primitivos compartilhados (`Segmented`, `Toast`,
  `Skeleton`, `EmptyState`, `Modal`, `Tooltip`, `IconButton`, `Icon`) (U-08,
  U-12).
- **R-P8** A casca funciona de 480 a 3440 px de CSS e sob zoom de 200%, com
  breakpoints de projeto e `@container` (U-07).
- **R-P9** Toda falha de ação aparece; o painel tem atalhos, paleta Ctrl+K,
  skeletons e abre mostrando o último snapshot (U-09, U-10, U-11).
- **R-P10** O que o dono quer ver de relance está no topo do detalhe: **em
  dia?**, **economia**, **agente usando?** (U-13).
- **R-P11** Produto: economia em moeda configurável, preview de `build_context`
  (a pergunta nunca é gravada), linha do tempo por sessão, saúde do índice com
  tendência, ícone de bandeja com estado e notificação de defasagem,
  auto-update, tema claro, instância única e CSP (U-14 e lacunas).

## 6. Ordem e dependências

```text
fase 14 (pendentes)        qualidade de recuperação — pré-requisito da fase 21
fase 19  velocidade/frescor  ──┐
fase 20  tokens              ──┼──> medição A/B (fase 20) fecha o ciclo
fase 21  recuperação v2      ──┘
fase 22  painel v2           (U-perf independe de tudo; U-produto lê a telemetria da fase 20)
```

Dentro de cada fase, o `README.md` traz o grafo exato de dependências. A ordem
global de execução, para quem roda em loop, está em
[`task/ROTEIRO-V2.md`](../task/ROTEIRO-V2.md).

## 7. Como a v2 é entregue

- **Uma tarefa = um commit** `tipo(escopo): descrição (RAGX-0xxx)`, em
  português, na branch `feat/v2`.
- **Nada de push, tag ou release** sem decisão humana.
- **Cada tarefa** termina com os checkboxes marcados, `ruff` e `mypy` limpos,
  a suíte rápida verde, a suíte `security/` verde, o CHANGELOG atualizado na
  mesma alteração e o número antes/depois registrado (princípio 4).
- **Se a tarefa crescer** além do escrito em "Fora de escopo", pare: abra uma
  tarefa nova em vez de improvisar.
- **Documentação divergente é bug**: se um número ou lista não bate com o
  código, o documento é corrigido na mesma alteração.
