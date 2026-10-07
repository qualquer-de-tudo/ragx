# Conexões por agente e onboarding multicliente

## Escopo

- Mover o interruptor global do Claude do header para Conexões.
- Organizar Conexões por abas: Ambiente, Claude Code, Codex, Gemini e Outros.
- Exibir clientes detectados e ligar/desligar MCP por cliente, usando o registro existente da CLI e backups.
- Reutilizar as abas no onboarding e explicar compatibilidade multicliente.
- Manter perfis e ajuste automático do Claude na sua aba.
- Não considerar ausência de Claude uma falha do ambiente.
- Verificar UI, IPC e CLI com testes e build.

## Fora de escopo

- Novos hooks ou atribuição de telemetria para Codex e Gemini.
- Alterar permissões, instalar agentes externos ou conectar sem clique da pessoa.
- Redesenhar outras telas, publicar release ou modificar o instalador.

## Validação concluída

- `npm run check`: lint, TypeScript e 2.032 testes do painel/IPC aprovados.
- `npm run build` e `npm run build:electron:ts`: aprovados.
- `uv run pytest -m "not slow" -n auto`: 2.135 aprovados, 6 ignorados.
- Ruff dos arquivos Python alterados e `git diff --check`: aprovados.
- Verificação visual: 21 medições sem problemas de layout, entre 450 e 1.280 px, temas claro/escuro e onboarding.
- `ragx mcp status --json` executado na instalação editável; detecção real dos clientes confirmada, sem alterar conexões.
