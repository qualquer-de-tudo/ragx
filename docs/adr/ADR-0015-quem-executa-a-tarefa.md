# ADR-0015 — Quem executa a tarefa

- **Status:** aceito
- **Data:** 2026-09-15
- **Contexto:** Fase 13 — Task Analyzer e Orquestração
- **Relacionado:** [ADR-0006](ADR-0006-mcp-casca-fina.md), [ADR-0012](ADR-0012-poder-do-agente-sobre-o-indice.md), [ADR-0014](ADR-0014-orquestracao-local-e-o-que-e-versionavel.md)

## Contexto

O fluxo pedido termina em "AI Agent executa a tarefa". Isso pressupõe que algum
componente chama um modelo, recebe código de volta e o aplica.

**O RAGX não tem um LLM, não chama um, e não deve passar a chamar.** Três
razões, e nenhuma é falta de esforço:

1. **Nunca foi esse o produto.** O RAGX indexa, protege e serve conhecimento
   local. Embutir um cliente de LLM traria chave de API, rede e custo por
   token para dentro de um sistema cujo argumento principal é rodar offline.
2. **`ragx.mcp` não pode falar com a rede** — invariante do ADR-0006,
   verificada por teste arquitetural. Um executor de IA dentro do servidor MCP
   quebraria exatamente a garantia que sustenta o resto.
3. **O agente já existe e é melhor nisso.** Quem fala com o usuário, edita
   arquivo, roda teste e abre pull request é o Claude Code (ou equivalente)
   que já está conectado ao RAGX por MCP. Duplicar isso seria construir um
   agente pior, por dentro.

Fingir o contrário produziria a pior entrega possível: um `TaskDispatcher` que
parece executar e na verdade só marca a tarefa como concluída.

## Decisão

**O RAGX é a fila e o árbitro. O agente é o executor.** O dispatcher entrega
trabalho; não faz trabalho.

```
  ragx worker                         agente de IA (via MCP)
  ───────────                         ──────────────────────
  resolve o DAG
  escolhe a próxima tarefa READY
  monta o contexto (Context Engine)
  marca QUEUED
        │
        │   ◄── claim_task ──────────  "me dá a próxima"
        │   ──  tarefa + contexto ─►
        │                             executa: lê, escreve, testa
        │   ◄── report_task_result ──  resultado estruturado
        ▼
  valida o resultado
  grava run, artefatos, decisões
  promove conhecimento
  libera as dependentes
```

O contrato entre os dois é o par de ferramentas MCP:

| Ferramenta | Direção | Efeito |
|---|---|---|
| `next_task` | leitura | a próxima tarefa executável, **sem** reivindicar |
| `claim_task` | escrita | reivindica com lease; devolve tarefa + contexto pronto |
| `report_task_result` | escrita | entrega o resultado; dispara validação e liberação |
| `release_task` | escrita | devolve sem executar (o agente desistiu) |

`claim_task` devolve o contexto já montado pelo Context Engine — o agente não
precisa (e não deve) reconstruir isso: ele recebe o pacote dentro do orçamento
de tokens, com as fontes.

## Modos de execução

**Interativo (o normal).** O agente está numa sessão com o humano. Ele chama
`claim_task`, executa, chama `report_task_result`. O humano vê tudo.

**Worker de fundo.** `ragx worker` roda por cron e faz **só** transição de
estado: promove `PENDING → READY` quando as dependências fecham, expira lease
morto, aplica retry com backoff, dispara agendamentos. Ele nunca executa uma
tarefa. É o que o pedido descreve na §15 — "o cron apenas acorda o RAGX".

**Manual.** `ragx task run TASK-004` imprime a tarefa e o contexto para o
humano colar onde quiser. Nenhuma mágica.

## O que isso muda no critério de sucesso

A §32 do pedido lista 20 passos. O RAGX entrega os passos 1 a 14 e 16 a 20
sozinho. O passo 15 — "executar o Agent" — é do agente, por contrato explícito.

Isso não é uma entrega parcial: é o desenho correto. O que se ganha é que a
fronteira fica visível. Uma tarefa `COMPLETED` significa que **um agente
reportou um resultado que passou na validação**, não que um componente do RAGX
decidiu sozinho que estava bom.

## Validação sem LLM

`TaskValidator` roda checagens determinísticas, e só:

- todo critério de aceite foi marcado com evidência?
- os arquivos declarados em `files_changed` existem e estão indexados?
- os arquivos tocados estão dentro de `files_scope`?
- nenhum arquivo tocado é bloqueado pelo Security Gate?
- o resultado declara teste quando `test_requirements` exige?
- o resultado tem `summary` e não está vazio?

Falhou uma → a tarefa volta para `FAILED` com o motivo, não para `COMPLETED`.
**Nenhum juízo sobre qualidade de código.** O RAGX não sabe julgar isso, e um
validador que finge saber é pior que nenhum: aprova o errado com autoridade.

Revisão de qualidade é do humano e do agente, com `quality/code-review.md` do
conhecimento base.

## Consequências

**Positivas**

- Zero chave de API, zero rede, zero custo por token dentro do RAGX.
- As invariantes do ADR-0006 permanecem intactas.
- Trocar de agente (Claude, outro, um humano) não muda nada na orquestração.
- Um `COMPLETED` significa algo verificável.

**Negativas aceitas**

- O RAGX não avança um projeto sozinho durante a noite. Ele mantém a fila
  pronta; alguém precisa aparecer para executar.
- O agente pode reportar um resultado falso. Mitigado pela validação
  determinística, que confere arquivos e escopo contra o índice — não é
  confiança cega, mas também não é prova.

## Alternativas descartadas

**Embutir um cliente de LLM.** Traria rede e credencial para dentro do RAGX,
quebraria o ADR-0006 e construiria um agente pior que o que já está conectado.

**Executar via `subprocess` chamando o CLI do agente.** Parece pequeno, e dá ao
RAGX execução de comando arbitrário — a capacidade que o ADR-0012 recusou
explicitamente. Não vale.

**Marcar `COMPLETED` sem validar.** Seria teatro. Uma fila que só avança números
não orquestra nada.
