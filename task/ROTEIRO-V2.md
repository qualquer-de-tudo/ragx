# Roteiro da v2

Fases 19 a 22, derivadas da [auditoria 24](../docs/24-auditoria-v2.md) e da
[spec 25](../docs/25-spec-v2.md). Este arquivo é a **fonte única** de IDs,
dependências e ordem de execução. Cada tarefa tem o seu arquivo na pasta da
fase; o `Depende de` do arquivo repete o desta tabela.

IDs continuam do `RAGX-0128`: **0129 a 0195**. Sequenciais e imutáveis.

Legenda de prioridade: **P0** bloqueante / maior ganho por esforço · **P1**
alta · **P2** média · **P3** baixa. `Est.` em dias de um desenvolvedor.
`Achado` aponta para a auditoria 24.

---

## Fase 19 — Velocidade e frescor ([pasta](fase-19-velocidade-e-frescor/))

| ID | Tarefa | Prio | Est. | Depende de | Achado |
|---|---|---|---|---|---|
| RAGX-0129 | Poda de diretórios com negação em `.gitignore` aninhado | P0 | 0,5d | — | M-01 |
| RAGX-0130 | Índice sem mudança: embedder preguiçoso e `git status` único | P0 | 0,5d | — | M-07, I-08 |
| RAGX-0131 | `refresh` incremental: `sync` só sob pedido, `rehydrate` opt-in, `serialize` só se mudou | P0 | 1d | 0129 | M-02, I-01 |
| RAGX-0132 | Ollama em `127.0.0.1` (adeus 2 s por requisição no Windows) | P0 | 0,25d | — | I-03 |
| RAGX-0133 | Arquivo travado no momento do save não some do índice | P0 | 0,5d | — | I-06 |
| RAGX-0134 | `load_index` vetorizado e cacheado por geração (`vec_gen`) | P0 | 0,5d | — | C-02 |
| RAGX-0135 | Cache do `build_context` com chave completa e versão confiável | P0 | 0,5d | 0134 | C-04 |
| RAGX-0136 | Busca usa o modelo configurado e avisa vetor parcial | P1 | 0,5d | 0134 | C-07, I-10 |
| RAGX-0137 | `scope` do MCP honrado ou recusado, nunca ignorado | P1 | 0,5d | — | C-05 |
| RAGX-0138 | `replace_for_document` por diff de chunk: embeddings e grafo sobrevivem a uma edição | P1 | 1d | — | C-06, I-07 |
| RAGX-0139 | Veredito de arquivo não indexável guardado (`file_verdicts`) | P1 | 0,5d | 0129 | I-05 |
| RAGX-0140 | `index_paths`: reindexar só os arquivos tocados | P0 | 1d | 0129, 0133, 0138 | I-02 |
| RAGX-0141 | Fila de toque, hook `PostToolUse` e `stale_paths` na busca | P0 | 1,5d | 0140, 0134 | I-02, M-10 |
| RAGX-0142 | Aquecer embedder e contador no servidor MCP | P1 | 0,5d | 0132 | M-06, C-08 |
| RAGX-0143 | Entrada leve para `claude hint` e `hook-run`; guarda no `post-checkout` | P1 | 1d | — | M-08, M-09 |
| RAGX-0144 | Clone novo usa os embeddings versionados em `knowledge/` | P1 | 1d | 0136 | I-04 |
| RAGX-0145 | Expansão do grafo: semeadura pelo topo, filtros e grau só dos visitados | P1 | 1d | — | C-03 |
| RAGX-0146 | Cache de embedding em SQLite, em lote | P2 | 0,75d | 0130 | I-09 |
| RAGX-0147 | Watcher barato: sem reconstruir o gate a cada ciclo | P2 | 0,75d | 0129, 0140 | I-11 |
| RAGX-0148 | `knowledge/` estável no Git: sem timestamp, sem reescrita igual | P2 | 0,5d | 0131 | I-12 |
| RAGX-0149 | Junction do Windows tratada como symlink | P1 | 0,25d | — | I-13 |
| RAGX-0150 | Micro-custos: `ragx context` sem `--tokens`, MMR vetorizado, query embutida uma vez | P3 | 0,5d | — | C-11, C-12 |
| RAGX-0151 | Grafo incremental por documento | P3 | 1,5d | 0138 | I-07 |
| RAGX-0152 | Primeiro índice em paralelo (pool de processos) | P3 | 1d | 0146 | I-14 |
| RAGX-0153 | Cache de modelos por usuário e trava com PID reutilizado | P3 | 0,5d | — | M-13 |

## Fase 20 — Economia de tokens ([pasta](fase-20-economia-de-tokens/))

| ID | Tarefa | Prio | Est. | Depende de | Achado |
|---|---|---|---|---|---|
| RAGX-0154 | `build_context`: uma só representação do conteúdo e contagem do que realmente sai | P0 | 1d | — | C-01, M-03 |
| RAGX-0155 | Respostas MCP compactas (sem indentação, sem repetição, sem `outputSchema` inútil) | P0 | 1d | 0154 | M-11 |
| RAGX-0156 | Telemetria honesta: `ok`, `err_code`, `resp_chars`, tokens reais | P1 | 0,5d | 0154 | M-12, M-03 |
| RAGX-0157 | Perfil `slim` do MCP: 6 ferramentas (`full` continua disponível) | P0 | 2d | 0137, 0154, 0155 | M-04 |
| RAGX-0158 | `instructions` ≤ 2 KB, descrições para Tool Search e lista estável | P1 | 0,5d | 0157 | R-T4 |
| RAGX-0159 | Dedupe de sessão: chunk já entregue volta como referência | P1 | 1,5d | 0154, 0157 | R-T5 |
| RAGX-0160 | Hook `PreToolUse` em `Grep\|Glob` lembra do índice uma vez por sessão | P1 | 1d | 0143, 0157 | M-05 |
| RAGX-0161 | Subagente `ragx-explorer` instalável | P2 | 0,5d | 0157 | M-05 |
| RAGX-0162 | Harness de A/B de economia (`claude -p` com e sem o MCP) | P1 | 2d | 0156, 0157 | M-03, S14 |
| RAGX-0163 | `ragx trial` e o painel com baseline honesto | P1 | 0,5d | 0154, 0156 | M-03 |
| RAGX-0164 | Hint de SessionStart enxuto e sem repetir em subagente | P2 | 0,5d | 0143, 0157 | M-08, M-12 |
| RAGX-0165 | Teto do `build_context` e `response_format: concise\|detailed` | P2 | 0,5d | 0154 | 7.2 #1 |

## Fase 21 — Recuperação v2 ([pasta](fase-21-recuperacao-v2/))

Herda as 14 tarefas pendentes da [fase 14](fase-14-evolucao-do-rag/) (0099,
0101, 0103–0114) como pré-requisito de qualidade; elas **não** são copiadas.

| ID | Tarefa | Prio | Est. | Depende de | Achado |
|---|---|---|---|---|---|
| RAGX-0166 | Prefixo contextual determinístico antes de embutir e indexar | P1 | 1d | 0104 | 7.2 #6 |
| RAGX-0167 | Conjunto-ouro derivado do git para avaliar recuperação | P2 | 2d | 0099 | 7.2 #11 |
| RAGX-0168 | Repo map compacto (PageRank sobre o grafo) como nível 0 | P2 | 2d | 0111, 0145 | 7.2 #9 |
| RAGX-0169 | Benchmark local de modelos de embedding e reranker de código | P2 | 1d | 0167, 0132 | 7.2 #4, #5 |
| RAGX-0170 | Índice por worktree/branch com chunks compartilhados por hash | P3 | 2d | 0138 | 7.2 #12 |

## Fase 22 — Painel v2 ([pasta](fase-22-painel-v2/))

| ID | Tarefa | Prio | Est. | Depende de | Achado |
|---|---|---|---|---|---|
| RAGX-0171 | Pausar pollers com a janela oculta; instância única | P0 | 0,5d | 0177 | U-04, U-14 |
| RAGX-0172 | Snapshot sem spawn de `git` | P0 | 0,5d | 0177 | U-02 |
| RAGX-0173 | Checagem de conexões barata | P0 | 0,75d | 0177 | U-03 |
| RAGX-0174 | Telemetria incremental e rotação do log da CLI | P0 | 0,75d | 0177 | U-01 |
| RAGX-0175 | Só re-renderiza o que mudou | P1 | 0,5d | 0177 | U-05 |
| RAGX-0176 | Remover o fallback que lê `knowledge.db` inteiro | P1 | 0,25d | — | U-06 |
| RAGX-0177 | Medir RAM e CPU do Electron em execução (linha de base) | P1 | 0,5d | — | seção 8 |
| RAGX-0178 | Tokens de design completos e contraste AA | P1 | 0,75d | — | U-08 |
| RAGX-0179 | Primitivos de UI compartilhados | P1 | 1d | 0178 | U-12 |
| RAGX-0180 | Toasts: toda falha de ação aparece | P1 | 0,5d | 0179 | U-09 |
| RAGX-0181 | Responsividade da casca de 480 a 3440 px e zoom 200% | P1 | 1d | 0178 | U-07 |
| RAGX-0182 | Skeletons e primeira pintura com o último snapshot | P2 | 0,5d | 0179 | U-11 |
| RAGX-0183 | Paleta Ctrl+K e atalhos | P2 | 1d | 0179 | U-10 |
| RAGX-0184 | Detalhe do projeto: em dia, economia, agente usando | P2 | 0,5d | 0179 | U-13 |
| RAGX-0185 | Acessibilidade: gráfico por teclado e setas nos grupos | P2 | 0,5d | 0179 | U-12 |
| RAGX-0186 | Economia em moeda configurável | P2 | 0,75d | 0156 | lacuna |
| RAGX-0187 | Preview do `build_context` no detalhe do projeto | P2 | 1,25d | 0154, 0179 | lacuna |
| RAGX-0188 | Linha do tempo de sessões na Atividade | P2 | 1d | 0156, 0179 | lacuna |
| RAGX-0189 | Saúde do índice com tendência | P2 | 0,5d | 0184 | lacuna |
| RAGX-0190 | Adoção: sessões que chamaram o RAGX e as que não | P2 | 0,5d | 0156, 0188 | M-05, S13 |
| RAGX-0191 | Bandeja com estado e notificação de defasagem | P3 | 1d | 0171, 0189 | lacuna |
| RAGX-0192 | Auto-update com `electron-updater` | P3 | 1d | 0171 | lacuna |
| RAGX-0193 | Tema claro | P3 | 1d | 0178, 0181 | lacuna |
| RAGX-0194 | CSP e menu mínimo | P2 | 0,25d | — | U-14 |
| RAGX-0195 | Fechar a v2: medir S1 a S14, publicar o relatório e conferir a documentação | P0 | 1d | todas as P0 e P1 | spec 3 |

---

## Ordem de execução

Ordem **linear** pensada para um loop sem supervisão: primeiro o que dá mais
ganho por esforço e não depende de nada; dentro de cada bloco, a ordem é a da
lista. **Nunca inicie uma tarefa com dependência aberta**; se a próxima da
lista estiver bloqueada, pule para a seguinte.

**Bloco 1 — ganhos rápidos de velocidade e correção** (≈ 4,5 d)
0132 · 0129 · 0130 · 0133 · 0149 · 0134 · 0135 · 0136 · 0137 · 0131

**Bloco 2 — tokens que saem** (≈ 3,5 d)
0154 · 0155 · 0156 · 0163 · 0165

**Bloco 3 — frescor de verdade** (≈ 6 d)
0138 · 0140 · 0141 · 0139 · 0142 · 0143 · 0145 · 0144

**Bloco 4 — conjunto mínimo de ferramentas e adoção** (≈ 6 d)
0157 · 0158 · 0159 · 0164 · 0160 · 0161 · 0162

**Bloco 5 — painel: desempenho** (≈ 4 d)
0177 · 0172 · 0173 · 0171 · 0174 · 0175 · 0176 · 0194

**Bloco 6 — painel: fundação e UX** (≈ 7 d)
0178 · 0179 · 0180 · 0181 · 0182 · 0183 · 0184 · 0185

**Bloco 7 — painel: produto** (≈ 7 d)
0186 · 0187 · 0188 · 0190 · 0189 · 0191 · 0192 · 0193

**Bloco 8 — o que sobra do core e a recuperação** (≈ 11 d)
0146 · 0147 · 0148 · 0150 · 0151 · 0152 · 0153 · 0166 · 0167 · 0168 · 0169 · 0170

**Fecho**: 0195.

A fase 14 (pendentes) pode ser intercalada pelo humano; o loop não a pega por
conta própria porque 0103 (trocar o modelo) muda o formato do índice e precisa
de decisão.

## O que o loop NÃO decide sozinho

Estas tarefas têm uma parte que **precisa de uma pessoa**. O loop entrega o que
é automatizável, deixa a tarefa em `review` (não `done`) e escreve o que falta
em "Notas":

- **0157** (perfil `slim`): o padrão do perfil só vira `slim` depois de a
  pessoa conferir os perfis de agente gerados. O loop entrega o perfil e o
  teste; **não** troca o padrão.
- **0162** (A/B com `claude -p`): gasta cota da conta. O loop entrega o
  harness, com modo `--dry-run` e simulado; **não** roda com chamadas reais.
- **0192** (auto-update): sem assinatura do `.exe` (RAGX-0124, adiada), o
  Windows alerta. O loop entrega atrás de configuração desligada por padrão.
- **0169** (benchmark de modelos): baixar modelos grandes pode ser pesado; o
  loop entrega o harness e só roda o que já está em disco.
- **0195** (fechar a v2): publica números; o loop os mede, mas uma pessoa
  decide o que anunciar.

## Prompt do loop

Cole no `/loop` (sem intervalo) para o Claude pegar a próxima tarefa e seguir:

```text
Você está implementando a v2 do RAGX, tarefa por tarefa. Regras:

1. Leia task/ROTEIRO-V2.md (ordem de execução) e docs/25-spec-v2.md (princípios).
2. Pegue a PRIMEIRA tarefa da ordem cujo Status seja `todo` e cujas dependências
   estejam todas `done`. Se não houver nenhuma, pare e diga por quê.
3. Leia o arquivo da tarefa inteiro. Marque Status `doing`.
4. Implemente SÓ o que está em "Entregáveis". "Fora de escopo" é lei: se a tarefa
   crescer, pare e anote em "Notas" em vez de improvisar.
5. Medições: registre o número ANTES de mexer e DEPOIS (CHANGELOG + "Andamento").
6. Marque cada `- [ ]` como `- [x]` conforme comprova (rodando, não supondo).
7. Antes de marcar `done`: uv run ruff check . · uv run mypy src/ragx/core
   src/ragx/security · uv run pytest -m "not slow" · uv run pytest tests/security
   (e, se tocou src/app: npm test, npm run lint, tsc dos dois projetos).
   Se algo falhar e você não resolver em 3 tentativas: Status `blocked`, escreva
   o motivo em "Notas", reverta o que deixou o repo quebrado e siga para a
   próxima tarefa independente.
8. CHANGELOG.md, seção [Não lançado], na MESMA alteração.
9. Um commit por tarefa: `tipo(escopo): descrição (RAGX-0xxx)`, em português,
   na branch feat/v2. NUNCA push, tag, release nem force. NUNCA toque em
   knowledge/ à mão; se um comando o regravar, não inclua no commit.
10. Segurança: o Security Gate roda antes do parser. Qualquer tarefa que mexa
    na leitura de arquivo precisa de teste em tests/security.
11. Tarefas listadas em "O que o loop NÃO decide sozinho": entregue a parte
    automatizável e deixe `review`.
```
