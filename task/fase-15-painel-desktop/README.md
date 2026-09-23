# Fase 15: Painel desktop

3 tarefas, todas nascidas do uso real do painel v2
([plano](../../docs/superpowers/plans/2026-09-23-painel-v2.md) ·
[spec](../../docs/superpowers/specs/2026-09-23-painel-v2-indice-por-branch-design.md)).

| ID | Tarefa | Prio | Est. | Status |
|---|---|---|---|---|
| [RAGX-0115](RAGX-0115-feedback-de-fila-nas-acoes-do-card.md) | Feedback de fila nas ações do card | P1 | 0,5d | `review` |
| [RAGX-0116](RAGX-0116-ollama-docker-ou-local-com-configuracao-automatica.md) | Ollama no Docker ou local, com configuração automática | P1 | ~3d | `review` |
| [RAGX-0117](RAGX-0117-grafo-3d-por-projeto-no-painel.md) | Grafo 3D por projeto no painel | P2 | 3 a 10d | `todo` |

## Itens menores conhecidos (ainda sem tarefa própria)

Registrados na revisão final do painel v2 e adiados de propósito:

- O card usa só o `status.json`, e o detalhe usa `ragx status --json`; para árvore suja os dois podem discordar (card "Atualizado", detalhe listando arquivos alterados)
- Caminho de hook desatualizado não é sinalizado com oferta de reinstalar
- Custo do ciclo de 5 s: 2 processos `git` por projeto e leitura completa do log de telemetria a cada ciclo
- O popover da fila não mostra o log completo da tarefa que falhou
- `status.json` nunca recebe `last_error` (parte A do núcleo), então o estado "Com problema" por erro é praticamente inalcançável
- Corrida estreita entre `exists()`, `copymode` e `os.replace` em `ragx.clients.registry._escrever`
