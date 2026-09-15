# Roadmap — fases, dependências e critérios de aceite

> **Nota sobre a numeração.** O plano original tinha uma inconsistência: o diagrama
> inicial colocava Hardening na Fase 9, enquanto as seções detalhadas e a tabela de
> prioridade iam até a Fase 10 (Git Sync = 9, Hardening = 10). Esta documentação adota
> a versão da tabela e acrescenta a **Fase 11 — Multiprojeto e Federação** —
> **12 fases, 0 a 11**. É essa a numeração usada em `task/`.

> **Duas restrições atravessam todas as fases**, e por isso não são fases próprias:
> o **orçamento de tamanho** ([16](16-orcamento-de-tamanho.md)) entra já na Fase 1,
> porque decide o que pode ser gravado; e a **identidade de projeto** entra na Fase 1
> porque, sem ela, a Fase 11 exigiria migrar todo o schema.

## Sequência

```text
FASE 0   Fundação + Security Gate           🔴 obrigatória
   ↓
FASE 1   Indexer + Knowledge Store          🔴 obrigatória
   ↓
FASE 2   Semantic + Hybrid Search           🔴 obrigatória   ◄── MVP VERTICAL AQUI
   ↓
FASE 3   Graph Knowledge                    🟠 alta
   ↓
FASE 4   Context Engine                     🔴 obrigatória para agentes
   ↓
FASE 5   Knowledge Dictionary               🟠 alta
   ↓
FASE 6   MCP                                🔴 obrigatória
   ↓
FASE 7   Agent Training                     🟠 alta
   ↓
FASE 8   Export / Import (.rag)             🟠 alta
   ↓
FASE 9   Git Sync / Merge                   🔴 obrigatória para time
   ↓
FASE 10  Hardening + Release                🔴 obrigatória
   ↓
FASE 11  Multiprojeto + Federação           🔴 obrigatória p/ microsserviços
   ↓
FASE 12  Autonomia + Conhecimento base      🟠 alta
   ↓
FASE 13  Task Analyzer + Orquestração       🟠 alta
```

A Fase 11 vem por último por dependência (precisa de `knowledge/` estável, Fase 9),
não por importância. Em ambiente com muitos repositórios ela pode ser **antecipada
para logo depois da Fase 6** — o que ela exige de antes é: identidade de projeto
(Fase 1), grafo referencial (Fase 3), dicionário (Fase 5) e MCP (Fase 6).

## O corte que importa: MVP vertical em Fase 0→2

Ao terminar a Fase 2 já existe produto utilizável:

```bash
ragx init
ragx index .
ragx search "minha pergunta"
```

com proteção contra segredos desde o primeiro commit. Só depois disso a evolução
segue por `graph → context → dictionary → MCP → agents`.

Construir infraestrutura por semanas sem um RAG funcionando ponta a ponta é o
modo de falha que este corte evita.

## Grafo de dependências

```text
F0 ──► F1 ──► F2 ──► F4 ──► F6 ──► F7
        │      │      ▲      ▲      ▲
        │      └──────┤      │      │
        │             │      │      │
        └──► F3 ──────┘      │      │
              │              │      │
              └──► F5 ───────┴──────┘
                    │
        F1 ──► F8 ◄─┘
        │       │
        └──► F9 ┘
                │
                ├──► F10
                │
                ▼
               F11  ◄── também precisa de F3 (grafo) e F6 (MCP)
```

Leituras práticas:

- **F4 (Context) depende de F2**; o grafo (F3) é um *enriquecedor* opcional — o
  Context Engine funciona sem ele, com resultado pior.
- **F6 (MCP) depende de F4**, porque `build_context` é a ferramenta que dá valor real.
- **F8 (Export) depende de F1**; embeddings e grafo são conteúdo opcional do pacote.
- **F9 (Git Sync) depende de F1**; a serialização estável de `knowledge/` é o requisito.
- **F10 consolida tudo** e é a única fase que pode mexer em qualquer módulo.
- **F11 (Multiprojeto) depende de F9** pelo `knowledge/` estável e da fatia de
  federação, mas o que ela consome de conhecimento vem de F3 (grafo referencial,
  que já detecta rotas e eventos) e F5 (dicionário). É a fase mais fácil de
  antecipar, e a única que pode ser entregue depois do release da F10.

## Tabela de prioridade

| Fase | Resultado | Prioridade | Depende de | Doc |
|------|-----------|-----------|-----------|-----|
| 0 | Security + Fundação | 🔴 obrigatória | — | [02](02-seguranca.md) |
| 1 | Indexação | 🔴 obrigatória | 0 | [04](04-indexacao.md) |
| 2 | Busca semântica/híbrida | 🔴 obrigatória | 1 | [05](05-busca.md) |
| 3 | Grafo | 🟠 alta | 1 | [06](06-grafo.md) |
| 4 | Context Engine | 🔴 obrigatória p/ agentes | 2 (3 opcional) | [07](07-context-engine.md) |
| 5 | Dictionary | 🟠 alta | 3 | [08](08-dictionary.md) |
| 6 | MCP | 🔴 obrigatória | 4, 5 | [09](09-mcp.md) |
| 7 | Agent Training | 🟠 alta | 5, 6 | [10](10-agent-training.md) |
| 8 | Export/Import `.rag` | 🟠 alta | 1, 3, 5 | [11](11-export-import.md) |
| 9 | Git Sync | 🔴 obrigatória p/ time | 1, 5 | [12](12-git-sync.md) |
| 10 | Hardening | 🔴 obrigatória | todas | [13](13-testes-hardening.md) |
| 11 | Multiprojeto + Federação | 🔴 obrigatória p/ microsserviços | 1, 3, 5, 6, 9 | [17](17-multiprojeto-e-federacao.md) |
| 12 | Autonomia + Conhecimento base | 🟠 alta | 1, 6, 9 | [18](18-conhecimento-base.md) · [19](19-watch-e-autonomia-do-agente.md) |
| 13 | Task Analyzer + Orquestração | 🟠 alta | 2, 4, 6, 12 | [20](20-task-analyzer.md) · [21](21-orquestracao-de-tarefas.md) |

## Critérios de aceite — resumo executivo

| Fase | Porta de saída |
|------|----------------|
| **0** | Fixture de segredos → `0 chunks · 0 embeddings · 0 nós · 0 MCP · 0 export`. `.env.example` e código legítimo **continuam** indexados. |
| **1** | `ragx index .` produz contagens corretas; 2ª execução não recria nada; IDs idênticos em Windows e Linux. |
| **2** | Busca encontra conteúdo semanticamente relacionado sem casar palavras; `hybrid > semantic > keyword` no `ragx eval`. |
| **3** | Consulta `vetor + grafo` acha o que a busca pura não acha; camadas 1-2 rodam sem nenhum LLM. |
| **4** | 10k tokens recuperados → ≤ 3k entregues, sem perder trecho-chave; toda fonte preservada. |
| **5** | `dictionary.json` gerado sem LLM, com `evidence` em todo item, regeneração byte-idêntica. |
| **6** | Agente externo opera só por MCP; teste arquitetural prova que MCP não toca filesystem. |
| **7** | Perfil gerado, versionável, avaliável; regras curadas à mão preservadas no retreino. |
| **8** | Export → import em máquina limpa reproduz busca e grafo; export falha em achado crítico. |
| **9** | `git pull && ragx sync` atualiza só o delta; `git diff knowledge/` vazio sem mudanças; `git clone && ragx search` responde offline com os vetores int8. |
| **10** | Zero `xfail` em segurança; CI verde em dois SOs; instalação limpa segue o README. |
| **11** | Agente em `order-service` obtém o contrato de `payment-service` **sem tê-lo clonado**; consumo sem provedor e divergência de método são reportados; projeto `private` invisível. |
| **13** | Pedido trivial NÃO cria projeto; pedido complexo documenta e decompõe antes; dependência aberta não executa; dependência concluída libera a próxima; dois workers disputando a mesma tarefa produzem UM vencedor; lease vencido é recuperado; retry segue a política e PARA; segredo não chega ao contexto do agente. |
| **12** | Fonte base **declarada** aparece como `@base/` na busca e a **não declarada** não aparece; segredo dentro dela é bloqueado; `knowledge/` não contém nenhum `@base/`; arquivo criado durante `ragx watch` entra no índice sozinho; agente reindexa via MCP sem ganhar acesso ao filesystem. |

## Regra de avanço entre fases

Uma fase só é considerada concluída quando:

1. Todos os critérios de aceite do doc da fase passam.
2. A suíte de segurança continua verde e o `xfail` correspondente à fase virou `pass`.
3. O doc da fase foi revisado contra o comportamento real do código
   (documentação divergente é dívida, não referência).
4. As tarefas da fase em `task/` estão fechadas ou explicitamente repriorizadas.

## Estimativa de esforço

Ordem de grandeza para **um desenvolvedor**, não compromisso de prazo:

| Fase | Esforço | Comentário |
|------|---------|-----------|
| 0 | ~1 semana | ruleset e fixture consomem mais que o código |
| 1 | ~1,5 semana | parsers e chunkers são o grosso |
| 2 | ~1 semana | fusão e avaliação |
| 3 | ~1,5 semana | camadas 1-2; a 3 é opcional |
| 4 | ~1 semana | compressão e orçamento exigem iteração |
| 5 | ~0,5 semana | maior parte é derivação do que já existe |
| 6 | ~0,5 semana | casca fina, por construção |
| 7 | ~1,5 semana | muito conteúdo curado, pouco código |
| 8 | ~1 semana | integridade e compatibilidade |
| 9 | ~1 semana | merge e serialização estável |
| 10 | ~1,5 semana | performance, robustez, release |
| 11 | ~2 semanas | hub, fatia de federação, resolução de vínculos, consulta cross-project |

**Fase 0→2 (MVP vertical): ~3,5 semanas.**

O orçamento de tamanho e a identidade de projeto acrescentam ~2 dias à Fase 1 e
~1 dia à Fase 9. É o custo de não ter que migrar o schema depois.
