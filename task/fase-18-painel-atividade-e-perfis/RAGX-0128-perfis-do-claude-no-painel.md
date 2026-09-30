# RAGX-0128: Perfis do Claude Code em Conexões

| | |
|---|---|
| **Fase** | 18: Painel — atividade ao vivo, lista de projetos e perfis do Claude |
| **Prioridade** | P1 |
| **Estimativa** | 1d |
| **Depende de** | descoberta de perfis da CLI (beta 4) |
| **Status** | `todo` |

## Objetivo

Quem roda mais de uma assinatura do Claude Code na mesma máquina (cada uma com
seu `CLAUDE_CONFIG_DIR`) precisa conectar o RAGX em todas, e ver e mudar cada
uma pelo painel. A CLI já acha `~/.claude` e `~/.claude-*`; perfil em outra
pasta ainda não tem como entrar.

## Entregáveis

- [ ] CLI: `ragx claude profiles add <pasta>` e `remove <pasta>`, guardados em
      `~/.ragx/claude-profiles.json`; a descoberta passa a incluí-los
- [ ] CLI: `ragx claude on|off --profile <id>` age num perfil só; `status --json`
      diz, por perfil, MCP ligado, dica instalada e se foi detectado ou adicionado
- [ ] Painel, Conexões: card "Claude Code" com um item por perfil (nome, pasta,
      interruptor), "Adicionar perfil" (escolher pasta) e "Remover" nos adicionados
- [ ] O interruptor global do header continua ligando e desligando todos

## Fora de escopo

- Criar um perfil novo do Claude Code (login, assinatura): a pasta tem de existir
- Outros clientes MCP (Cursor, Windsurf...) por perfil

## Critérios de aceite

- [ ] Adicionar uma pasta fora de `~/.claude-*` e ligar só nela grava o MCP e a dica só ali
- [ ] Desligar um perfil não mexe nos outros
- [ ] Tirar uma pasta da lista não mexe na configuração dela; para tirar o RAGX de lá, desligar antes

## Testes

Unit da CLI (add/remove/on/off por perfil, arquivo inválido); vitest do card.

## Definition of Done

- [ ] Critérios verificados
- [ ] CHANGELOG na mesma alteração
- [ ] docs/14-cli.md atualizado
