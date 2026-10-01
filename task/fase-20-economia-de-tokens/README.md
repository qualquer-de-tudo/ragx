# Fase 20: Economia de tokens

12 tarefas, derivadas da [auditoria 24](../../docs/24-auditoria-v2.md) (seções 3.C-01, 4 e 7.2) e da [spec 25](../../docs/25-spec-v2.md) (seção 5.2, requisitos R-T1 a R-T8). O produto existe para economizar tokens, e hoje a promessa é quebrada por baixo e medida por cima.

Um `build_context` de 3.000 tokens entrega **7.684** no fio (2,6×): o conteúdo sai duas vezes (`fragments` e `markdown`), em JSON com `indent=2`, e a telemetria grava o orçamento como se fosse a entrega real, então a economia que o painel mostra está superestimada (C-01, M-03). O conjunto de 33 ferramentas MCP tem 28 sem nenhuma chamada nos logs e custa 2.660 tokens por turno quando não é deferred; um protótipo de 6 ferramentas custa 419 (−84%, M-04). E quase ninguém chama o RAGX: 3 de 38 sessões em projetos indexados (M-05), porque a ferramenta chega deferred e Grep e Read já estão carregados. A economia real contra um agente que usa Grep é **desconhecida** (o baseline é o arquivo inteiro), e a fase termina medindo isso por A/B (S14). Metas medíveis: S1, S2, S13 e S14 da spec 25.

## Tarefas

| ID | Tarefa | Prio | Est. | Status |
|---|---|---|---|---|
| [RAGX-0154](RAGX-0154-build-context-uma-so-representacao-do-conteudo-e-contagem-do-que-realmente-sai.md) | `build_context`: uma só representação do conteúdo e contagem do que realmente sai | P0 | 1d | `done` |
| [RAGX-0155](RAGX-0155-respostas-mcp-compactas-sem-indentacao-sem-repeticao-sem-outputschema-inutil.md) | Respostas MCP compactas (sem indentação, sem repetição, sem `outputSchema` inútil) | P0 | 1d | `done` |
| [RAGX-0156](RAGX-0156-telemetria-honesta-ok-err-code-resp-chars-tokens-reais.md) | Telemetria honesta: `ok`, `err_code`, `resp_chars`, tokens reais | P1 | 0,5d | `done` |
| [RAGX-0157](RAGX-0157-perfil-slim-do-mcp-6-ferramentas-full-continua-disponivel.md) | Perfil `slim` do MCP: 6 ferramentas (`full` continua disponível) | P0 | 2d | `review` |
| [RAGX-0158](RAGX-0158-instructions-ate-2-kb-descricoes-para-tool-search-e-lista-estavel.md) | `instructions` ≤ 2 KB, descrições para Tool Search e lista estável | P1 | 0,5d | `todo` |
| [RAGX-0159](RAGX-0159-dedupe-de-sessao-chunk-ja-entregue-volta-como-referencia.md) | Dedupe de sessão: chunk já entregue volta como referência | P1 | 1,5d | `todo` |
| [RAGX-0160](RAGX-0160-hook-pretooluse-em-grep-glob-lembra-do-indice-uma-vez-por-sessao.md) | Hook `PreToolUse` em `Grep\|Glob` lembra do índice uma vez por sessão | P1 | 1d | `todo` |
| [RAGX-0161](RAGX-0161-subagente-ragx-explorer-instalavel.md) | Subagente `ragx-explorer` instalável | P2 | 0,5d | `todo` |
| [RAGX-0162](RAGX-0162-harness-de-ab-de-economia-claude-p-com-e-sem-o-mcp.md) | Harness de A/B de economia (`claude -p` com e sem o MCP) | P1 | 2d | `todo` |
| [RAGX-0163](RAGX-0163-ragx-trial-e-o-painel-com-baseline-honesto.md) | `ragx trial` e o painel com baseline honesto | P1 | 0,5d | `done` |
| [RAGX-0164](RAGX-0164-hint-de-sessionstart-enxuto-e-sem-repetir-em-subagente.md) | Hint de SessionStart enxuto e sem repetir em subagente | P2 | 0,5d | `todo` |
| [RAGX-0165](RAGX-0165-teto-do-build-context-e-response-format-concise-detailed.md) | Teto do `build_context` e `response_format: concise\|detailed` | P2 | 0,5d | `done` |

## Dependências

```text
0154 ──> 0155
0154 ──> 0156
0154 ──> 0159 (também depende de 0157)
0154 ──> 0163 (também depende de 0156)
0154 ──> 0165
0137 (fase 19) ──┐
0154 ────────────┼──> 0157
0155 ────────────┘
0156 ──> 0162 (também depende de 0157)
0157 ──> 0158
0157 ──> 0159
0157 ──> 0160 (também depende de 0143, fase 19)
0157 ──> 0161
0157 ──> 0162
0157 ──> 0164 (também depende de 0143, fase 19)
```

## Ordem sugerida

Trechos do [ROTEIRO-V2.md](../ROTEIRO-V2.md) que contêm tarefas desta fase. Dentro de cada bloco, a ordem é a da lista. **Nunca inicie uma tarefa com dependência aberta**; se a próxima da lista estiver bloqueada, pule para a seguinte.

**Bloco 2 — tokens que saem** (≈ 3,5 d)
0154 · 0155 · 0156 · 0163 · 0165

**Bloco 4 — conjunto mínimo de ferramentas e adoção** (≈ 6 d)
0157 · 0158 · 0159 · 0164 · 0160 · 0161 · 0162

Duas tarefas têm uma parte que precisa de uma pessoa e terminam em `review`: a 0157 (o padrão do perfil só vira `slim` depois de conferir os perfis de agente gerados), a 0162 (o A/B com `claude -p` gasta cota da conta; o loop entrega o harness com `--dry-run` e simulado, sem chamadas reais).
