# RAGX-0202 — Instruções para Codex e Gemini CLI

| | |
|---|---|
| **Fase** | 25 — Economia real |
| **Prioridade** | P1 |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `review` |

## Objetivo

Codex, Gemini CLI e Cursor não têm a dica de início de sessão nem o lembrete do Claude Code: só recebem o MCP e as
instruções do servidor, que o modelo costuma ignorar. Esses clientes leem um arquivo de instruções do usuário
(Codex: `~/.codex/AGENTS.md`; Gemini: `~/.gemini/GEMINI.md`). Ao ligar o RAGX num deles, um bloco curto e
gerenciado entra nesse arquivo; ao desligar, sai.

## Entregáveis

- [x] Bloco delimitado (`<!-- ragx:inicio -->` … `<!-- ragx:fim -->`), curto, que diz quando usar o RAGX antes de
      grep/leitura; idempotente; preserva tudo o que a pessoa escreveu fora dele
- [x] Ligado e desligado junto com o registro MCP do cliente (`ragx mcp install|uninstall` e o interruptor do painel, que usa o mesmo registro)
- [x] `ragx mcp status --json` diz se o bloco está presente

## Fora de escopo

- Escrever no arquivo de instruções de um projeto (só o do usuário)
- Cursor por regra de projeto (`.cursor/rules`): fica para quando houver pedido

## Critérios de aceite

- [x] Testes: ligar cria o bloco, ligar de novo não duplica, desligar remove só o bloco, texto alheio intacto
