# RAGX-0197 — Hooks automáticos, Conexões refeita, "Como funciona" no fim da barra e Atividade paginada

| | |
|---|---|
| **Fase** | 23 — Pós-lançamento |
| **Prioridade** | P1 — alta |
| **Estimativa** | 2d |
| **Depende de** | RAGX-0141, RAGX-0160, RAGX-0192 |
| **Documentação** | [14-cli.md](../../docs/14-cli.md) (`ragx claude heal`) · [GUIA-DE-USO.md](../../docs/GUIA-DE-USO.md) · [26-resultados-v2.md](../../docs/26-resultados-v2.md) |
| **Status** | `review` |

## Objetivo

Depois de algumas horas de uso real da 1.0.0 num projeto de terceiros (perfil `empresa`), a análise achou três coisas: (1) **os hooks de edição e de lembrete não estavam instalados em nenhum dos três perfis do Claude Code** (ligados numa versão antiga), então o índice ficava 23 arquivos defasado e as buscas devolviam a versão antiga de arquivos editados; (2) o `status.json` deixava um `.tmp` órfão quando o painel o tinha aberto no Windows; (3) a tela Conexões estava pesada e o "Como funciona" era um parágrafo solto no meio da barra. Pediu-se ainda paginar a Atividade, que crescerá com a janela.

## Entregáveis

- [x] **Medir primeiro**: `ragx claude status --json` mostrou `touch: false` e `nudge: false` nos três perfis; `ragx claude heal --dry-run` os apontou como faltando; `ragx search` por um arquivo novo não-commitado não o achou (ausente do índice)
- [x] `status_file.write_status`: `os.replace` tenta de novo (5 vezes) e o `.tmp` é apagado se a troca falha; dois testes
- [x] `ragx claude heal [--json] [--command] [--profile] [--dry-run]`: completa hook de início, aviso de edição e lembrete **só em perfil com o MCP registrado**; respeita `ragx claude on --no-touch|--no-nudge|--no-hint` (`~/.ragx/claude-optout.json`); idempotente; preserva hooks da pessoa
- [x] Painel: `electron/auto-setup.ts` roda o `heal` e enfileira `hooks-install` nos projetos com `hooksInstalled === false`, ao abrir (8 s), a cada 15 min e quando um snapshot mostra projeto sem hooks; retentativa do mesmo projeto só depois de 30 min; preferência `autoSetup` (ligada por padrão); IPC `getAutoSetup`/`runAutoSetup`/`onAutoSetup`
- [x] Conexões: card "Ajuste automático" (estado do Claude e do git, última rodada, interruptor, "Ajustar agora"), faixa de estado nos cartões, fatos em linha, comando manual recolhido, hooks por perfil em selos
- [x] "Como funciona" no fim da barra lateral e refeito (caminho do dado em 5 passos, o que mantém o índice em dia, onde ficam os dados); texto do onboarding cita o hook de edição
- [x] Atividade paginada (50 eventos / 20 sessões por página, `Pager`, filtro volta à página 1)
- [x] Docs (`14-cli`, `GUIA-DE-USO`) e CHANGELOG

## Fora de escopo

- Ampliar a janela da Atividade além de 24 h / 500 eventos (a paginação já protege o DOM, mas o processo principal continua guardando só isso em memória)
- Descobrir por que o Claude Code removeu o MCP da sessão às 13:16Z (o log do cliente não registra; o servidor do RAGX não tem lógica de sair sozinho)
- Ligar o RAGX num perfil desligado (decisão da pessoa) ou instalar hooks de git em pasta que não é repositório
- Reescrever a leitura do `status.json` no painel

## Critérios de aceite

- [x] Num perfil com o RAGX ligado e sem `touch`/`nudge`, `ragx claude heal` instala os dois; em perfil desligado não toca em nada
- [x] `ragx claude on --no-touch` seguido de `heal` não reinstala o `touch`; `on` sem flags apaga a recusa
- [x] `write_status` com `os.replace` falhando duas vezes grava, e falhando sempre devolve `None` sem deixar `.tmp`
- [x] 10 mil eventos na Atividade renderizam 50 linhas
- [x] `ruff`, `mypy`, suíte Python, `tests/security`, `npm run check` e `tsc` do Electron verdes
- [ ] **Não verificado**: o painel empacotado rodando o ajuste (só a lógica e o `heal` por CLI foram testados); a atualização automática do painel de 1.0.0 para 1.0.1 (ver Andamento)

## Testes

- [x] `tests/unit/test_claude_heal.py` (7), `tests/integration/test_status_file.py` (+2)
- [x] `electron/__tests__/auto-setup.test.ts` (11), `settings.test.ts`, `ipc.test.ts`, `preload.test.ts`
- [x] `AutoSetupCard.test.tsx`, `useAutoSetup.test.ts`, `Pager.test.tsx`, `ActivityPage.test.tsx` (paginação), `HowItWorksPage.test.tsx`, `ClaudeProfiles.test.tsx`, `ConnectionsPage.test.tsx`, `shell.test.tsx`
- [x] Verificação visual com `scripts/visual-check.mjs` (Conexões, Como funciona e Atividade em 1280 e 600 px, sem estouro)

## Andamento

- 2026-10-02 — Análise do projeto `sturdy-bassoon` e implementação. Achado extra: `docs` e `CHANGELOG` tinham as entradas de `[Não lançado]` movidas para `[1.0.0]` pelo `versao.py`; a seção ficou vazia até esta tarefa.
