# RAGX-0125: Registro de atividade — cliente e perfil no MCP, comandos da CLI

| | |
|---|---|
| **Fase** | 18: Painel — atividade ao vivo, lista de projetos e perfis do Claude |
| **Prioridade** | P1 |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Status** | `todo` |

## Objetivo

A tela de atividade (RAGX-0126) precisa saber, de cada chamada, **quem** chamou.
Hoje `.ragx/logs/mcp.jsonl` diz ferramenta, tempo e tokens, mas não o cliente
nem o perfil do Claude Code, e os comandos da CLI rodados no terminal não deixam
rastro nenhum.

## Entregáveis

- [ ] `mcp.jsonl` ganha `client` (nome do cliente MCP, do `initialize`) e
      `profile` (perfil do Claude Code pelo `CLAUDE_CONFIG_DIR` herdado: `padrão`
      sem a variável, o sufixo de `~/.claude-<nome>`, ou o nome da pasta)
- [ ] `.ragx/logs/cli.jsonl`: uma linha por comando de consulta rodado à mão
      (`search`, `context`, `graph-search`, `chunk`, `trial`), com `ts`,
      `command`, `ms`, `ok` e `project`; nunca a consulta nem os argumentos
- [ ] `ragx claude hint` registra `session_start` (com o perfil) quando há índice
- [ ] Chamadas feitas pelo painel não entram (`RAGX_CALLER=painel`), senão o
      `ragx status` a cada poucos segundos afogaria o feed

## Fora de escopo

- Gravar a consulta, os argumentos ou o conteúdo devolvido (nunca)
- Indexações: já ficam em `index_runs` e no `status.json` (`running`)
- A tela (RAGX-0126)

## Critérios de aceite

- [ ] Chamada MCP de um Claude com `CLAUDE_CONFIG_DIR=~/.claude-empresa` grava `profile: "empresa"`
- [ ] `ragx search x` no terminal grava uma linha sem a palavra `x`
- [ ] Comando rodado pelo painel não grava nada

## Testes

Unit do servidor (entrada de log com cliente e perfil), da CLI (linha gravada,
sem a consulta; nada com `RAGX_CALLER=painel`) e do `hint`.

## Definition of Done

- [ ] Critérios verificados
- [ ] CHANGELOG na mesma alteração
- [ ] docs/14-cli.md atualizado
