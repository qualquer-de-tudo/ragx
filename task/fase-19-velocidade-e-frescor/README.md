# Fase 19: Velocidade e frescor

25 tarefas, derivadas da [auditoria 24](../../docs/24-auditoria-v2.md) (seções 3, 4 e 5) e da [spec 25](../../docs/25-spec-v2.md) (seção 5.1, requisitos R-V1 a R-V13). Cobrem o caminho quente de leitura e o de escrita: poda de diretórios, embedder, `refresh`, `load_index`, caches, `replace_for_document`, hooks e frescor de edições não commitadas.

O produto promete **não deixar o Claude lento** e **nunca raciocinar sobre código velho**, e dois defeitos pequenos quebram as duas promessas. A poda de diretórios fica desligada em subárvore com `.gitignore` aninhado que tenha negação (M-01): 19.120 arquivos vistos para 643 mantidos, 12,8 s dos 15 s de uma indexação sem mudança. O `refresh` por MCP roda índice e `sync` completo e regrava `knowledge/` (M-02, I-01): 26 s em processo, 72 a 91 s via MCP, contra 1,0 s do `index` puro. Somam-se `localhost` do Ollama custando ~2 s por requisição no Windows (I-03), `load_index` em laço Python em toda busca (C-02: 69 a 80 ms, cerca de 75% da busca quente), cache do `build_context` que serviu o pack de outro filtro (C-04) e nenhuma reindexação por caminho: edição não commitada nunca entra no índice por conta própria (I-02, M-10). As metas medíveis são S4 a S10 e S12 da spec 25.

## Tarefas

| ID | Tarefa | Prio | Est. | Status |
|---|---|---|---|---|
| [RAGX-0129](RAGX-0129-poda-de-diretorios-com-negacao-em-gitignore-aninhado.md) | Poda de diretórios com negação em `.gitignore` aninhado | P0 | 0,5d | `done` |
| [RAGX-0130](RAGX-0130-indice-sem-mudanca-embedder-preguicoso-e-git-status-unico.md) | Índice sem mudança: embedder preguiçoso e `git status` único | P0 | 0,5d | `done` |
| [RAGX-0131](RAGX-0131-refresh-incremental-sync-sob-pedido-rehydrate-opt-in-serialize-so-se-mudou.md) | `refresh` incremental: `sync` só sob pedido, `rehydrate` opt-in, `serialize` só se mudou | P0 | 1d | `todo` |
| [RAGX-0132](RAGX-0132-ollama-em-127-0-0-1-adeus-2-s-por-requisicao-no-windows.md) | Ollama em `127.0.0.1` (adeus 2 s por requisição no Windows) | P0 | 0,25d | `done` |
| [RAGX-0133](RAGX-0133-arquivo-travado-no-momento-do-save-nao-some-do-indice.md) | Arquivo travado no momento do save não some do índice | P0 | 0,5d | `done` |
| [RAGX-0134](RAGX-0134-load-index-vetorizado-e-cacheado-por-geracao-vec-gen.md) | `load_index` vetorizado e cacheado por geração (`vec_gen`) | P0 | 0,5d | `todo` |
| [RAGX-0135](RAGX-0135-cache-do-build-context-com-chave-completa-e-versao-confiavel.md) | Cache do `build_context` com chave completa e versão confiável | P0 | 0,5d | `todo` |
| [RAGX-0136](RAGX-0136-busca-usa-o-modelo-configurado-e-avisa-vetor-parcial.md) | Busca usa o modelo configurado e avisa vetor parcial | P1 | 0,5d | `todo` |
| [RAGX-0137](RAGX-0137-scope-do-mcp-honrado-ou-recusado-nunca-ignorado.md) | `scope` do MCP honrado ou recusado, nunca ignorado | P1 | 0,5d | `todo` |
| [RAGX-0138](RAGX-0138-replace-for-document-por-diff-de-chunk-embeddings-e-grafo-sobrevivem-a-uma-edicao.md) | `replace_for_document` por diff de chunk: embeddings e grafo sobrevivem a uma edição | P1 | 1d | `todo` |
| [RAGX-0139](RAGX-0139-veredito-de-arquivo-nao-indexavel-guardado-file-verdicts.md) | Veredito de arquivo não indexável guardado (`file_verdicts`) | P1 | 0,5d | `todo` |
| [RAGX-0140](RAGX-0140-index-paths-reindexar-so-os-arquivos-tocados.md) | `index_paths`: reindexar só os arquivos tocados | P0 | 1d | `todo` |
| [RAGX-0141](RAGX-0141-fila-de-toque-hook-posttooluse-e-stale-paths-na-busca.md) | Fila de toque, hook `PostToolUse` e `stale_paths` na busca | P0 | 1,5d | `todo` |
| [RAGX-0142](RAGX-0142-aquecer-embedder-e-contador-no-servidor-mcp.md) | Aquecer embedder e contador no servidor MCP | P1 | 0,5d | `todo` |
| [RAGX-0143](RAGX-0143-entrada-leve-para-claude-hint-e-hook-run-guarda-no-post-checkout.md) | Entrada leve para `claude hint` e `hook-run`; guarda no `post-checkout` | P1 | 1d | `todo` |
| [RAGX-0144](RAGX-0144-clone-novo-usa-os-embeddings-versionados-em-knowledge.md) | Clone novo usa os embeddings versionados em `knowledge/` | P1 | 1d | `todo` |
| [RAGX-0145](RAGX-0145-expansao-do-grafo-semeadura-pelo-topo-filtros-e-grau-so-dos-visitados.md) | Expansão do grafo: semeadura pelo topo, filtros e grau só dos visitados | P1 | 1d | `todo` |
| [RAGX-0146](RAGX-0146-cache-de-embedding-em-sqlite-em-lote.md) | Cache de embedding em SQLite, em lote | P2 | 0,75d | `todo` |
| [RAGX-0147](RAGX-0147-watcher-barato-sem-reconstruir-o-gate-a-cada-ciclo.md) | Watcher barato: sem reconstruir o gate a cada ciclo | P2 | 0,75d | `todo` |
| [RAGX-0148](RAGX-0148-knowledge-estavel-no-git-sem-timestamp-sem-reescrita-igual.md) | `knowledge/` estável no Git: sem timestamp, sem reescrita igual | P2 | 0,5d | `todo` |
| [RAGX-0149](RAGX-0149-junction-do-windows-tratada-como-symlink.md) | Junction do Windows tratada como symlink | P1 | 0,25d | `done` |
| [RAGX-0150](RAGX-0150-micro-custos-ragx-context-sem-tokens-mmr-vetorizado-query-embutida-uma-vez.md) | Micro-custos: `ragx context` sem `--tokens`, MMR vetorizado, query embutida uma vez | P3 | 0,5d | `todo` |
| [RAGX-0151](RAGX-0151-grafo-incremental-por-documento.md) | Grafo incremental por documento | P3 | 1,5d | `todo` |
| [RAGX-0152](RAGX-0152-primeiro-indice-em-paralelo-pool-de-processos.md) | Primeiro índice em paralelo (pool de processos) | P3 | 1d | `todo` |
| [RAGX-0153](RAGX-0153-cache-de-modelos-por-usuario-e-trava-com-pid-reutilizado.md) | Cache de modelos por usuário e trava com PID reutilizado | P3 | 0,5d | `todo` |

## Dependências

```text
0129 ──> 0131 ──> 0148
0129 ──> 0139
0129 ──> 0147 (também depende de 0140)
0130 ──> 0146 ──> 0152
0132 ──> 0142
0133 ──┐
0138 ──┴──> 0140 ──> 0141 (0140 também depende de 0129; 0141 de 0134)
             0140 ──> 0147
0138 ──> 0151
0134 ──> 0135
0134 ──> 0136 ──> 0144
0134 ──> 0141
independentes: 0137, 0143, 0145, 0149, 0150, 0153
```

## Ordem sugerida

Trechos do [ROTEIRO-V2.md](../ROTEIRO-V2.md) que contêm tarefas desta fase. Dentro de cada bloco, a ordem é a da lista. **Nunca inicie uma tarefa com dependência aberta**; se a próxima da lista estiver bloqueada, pule para a seguinte.

**Bloco 1 — ganhos rápidos de velocidade e correção** (≈ 4,5 d)
0132 · 0129 · 0130 · 0133 · 0149 · 0134 · 0135 · 0136 · 0137 · 0131

**Bloco 3 — frescor de verdade** (≈ 6 d)
0138 · 0140 · 0141 · 0139 · 0142 · 0143 · 0145 · 0144

**Bloco 8 — o que sobra do core e a recuperação** (≈ 11 d; as tarefas desta fase são 0146 a 0153)
0146 · 0147 · 0148 · 0150 · 0151 · 0152 · 0153 · 0166 · 0167 · 0168 · 0169 · 0170
