# RAGX-0128: Perfis do Claude Code em Conexões

| | |
|---|---|
| **Fase** | 18: Painel — atividade ao vivo, lista de projetos e perfis do Claude |
| **Prioridade** | P1 |
| **Estimativa** | 1d |
| **Depende de** | descoberta de perfis da CLI (beta 4) |
| **Status** | `done` |

## Objetivo

Quem roda mais de uma assinatura do Claude Code na mesma máquina (cada uma com
seu `CLAUDE_CONFIG_DIR`) precisa conectar o RAGX em todas, e ver e mudar cada
uma pelo painel. A CLI já acha `~/.claude` e `~/.claude-*`; perfil em outra
pasta ainda não tem como entrar.

## Entregáveis

- [x] CLI: `ragx claude profiles add <pasta>` e `remove <pasta>`, guardados em
      `~/.ragx/claude-profiles.json`; a descoberta passa a incluí-los
- [x] CLI: `ragx claude on|off --profile <id>` age num perfil só; `status --json`
      diz, por perfil, MCP ligado, dica instalada e se foi detectado ou adicionado
- [x] Painel, Conexões: card "Claude Code" com um item por perfil (nome, pasta,
      interruptor), "Adicionar perfil" (escolher pasta) e "Remover" nos adicionados
- [x] O interruptor global do header continua ligando e desligando todos

## Fora de escopo

- Criar um perfil novo do Claude Code (login, assinatura): a pasta tem de existir
- Outros clientes MCP (Cursor, Windsurf...) por perfil

## Critérios de aceite

- [x] Adicionar uma pasta fora de `~/.claude-*` e ligar só nela grava o MCP e a dica só ali
- [x] Desligar um perfil não mexe nos outros
- [x] Tirar uma pasta da lista não mexe na configuração dela (`profiles remove`); no painel, "Remover" desliga antes, porque quem clica espera o RAGX sair daquela conta

## Testes

Unit da CLI (add/remove/on/off por perfil, arquivo inválido); vitest do card.

## Definition of Done

- [x] Critérios verificados
- [x] CHANGELOG na mesma alteração
- [x] docs/14-cli.md atualizado
