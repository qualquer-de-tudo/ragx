# Fase 16: Instalador completo do painel

1 tarefa, nascida do uso real: logo após instalar o `.exe`, o passo 2 do
assistente mostrava RAGX CLI, Claude Code e Ollama como "Não conectado"
([plano](../docs/superpowers/plans/2026-09-23-instalador-completo.md) ·
[spec](../docs/superpowers/specs/2026-09-23-instalador-completo-design.md) ·
[ADR-0016](../docs/adr/ADR-0016-instalador-completo-do-painel.md)).

# RAGX-0118: O `.exe` do painel instala a CLI e a desinstala

| | |
|---|---|
| **Fase** | 16: Instalador completo do painel |
| **Prioridade** | P1 |
| **Estimativa** | ~2d |
| **Depende de** | RAGX-0116 |
| **Documentação** | [src/app/README.md](../src/app/README.md#empacotando) · [install/README.md](../install/README.md) |
| **Status** | `review` |

## Objetivo

Só com o `.exe`, numa máquina limpa e com internet, chegar a "RAGX CLI verde" e
"Claude Code registrável em um clique"; e poder desinstalar tudo.

## Entregáveis

- [x] `scripts/prepare-bundle.mjs`: wheel + `uv.exe` de versão fixa com SHA256 conferido + `bundle.json`
- [x] `electron-builder.yml` (`extraResources`, `nsis.include`) e `npm run bundle`
- [x] `build/installer.nsh`: `customInstall` (`--bootstrap`) e `customRemoveFiles` (duas perguntas, `--uninstall-cli`)
- [x] `electron/bootstrap/` (bundle, PATH, desinstalação), `--bootstrap` e `--uninstall-cli` no `main.ts`, ação "Instalar / Tentar de novo" no card RAGX CLI
- [x] `ragx mcp uninstall --client <nome>` na CLI Python
- [x] Job `painel-windows` na release (smoke de instalar, verificar, desinstalar) e instalador anexado à release
- [ ] Validação final da UI com Playwright (passo 2 do assistente verde após o bootstrap)

## Fora de escopo

- macOS e Linux (continuam com `install.sh`)
- Embutir ou instalar o Ollama (segue o fluxo `ollama-use-native` já existente)
- Instalar o Claude Code (só registra o MCP se ele já existir)
- Modo offline (o `uv` precisa de rede para o Python e as dependências)
- Assinatura de código e auto-update (o hash do bundle protege contra corrupção, não adulteração)
- Remover `.ragx/` de projetos ou o Ollama na desinstalação

## Critérios de aceite

- Instalação silenciosa (`/S`) deixa `ragx --version` e `ragx mcp serve --help` funcionando com `~\.local\bin` no PATH
- Falha do bootstrap não falha a instalação e o painel oferece "Tentar de novo"
- Desinstalar com `--remove-cli` remove `ragx.exe`; sem a flag em `/S`, não remove
- `~\.ragx` só é removido com `--remove-data` (ou "Sim" na segunda pergunta)
- Atualizar o painel por cima não remove a CLI nem pergunta nada
