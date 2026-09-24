# Instalador completo do RAGX Painel — design

Data: 2026-09-23 · Escopo: Windows · Origem: painel mostrava RAGX CLI, Claude Code e
Ollama "Não conectado" logo após instalar o `.exe`.

## Problema

O `RAGX Painel Setup.exe` (NSIS) instala só o Electron. A CLI `ragx`, o `uv`, o
PATH e o registro do MCP vêm do `install/install.ps1`, que o usuário final não
roda. Resultado: passo 2 do assistente vermelho nos três cards.

## Objetivo

Só com o `.exe`, numa máquina limpa e com internet, o usuário chega a "RAGX CLI
verde" e "Claude Code registrável em um clique"; o Ollama fica a um clique
(fluxo `ollama-use-native` já existente). E consegue desinstalar tudo.

## Decisões (aprovadas na conversa)

1. Pode usar internet: o `uv` baixa Python 3.12 e dependências.
2. Abordagem C: NSIS dispara `--bootstrap`; o painel reusa a mesma rotina como
   "Reparar" quando `resolveRagx()` é `null`. Lógica só em TypeScript.
3. Desinstalador com duas caixas: remover a CLI (padrão marcada) e remover os
   dados do hub `~\.ragx` (padrão desmarcada). Ollama e `.ragx/` dos projetos
   nunca são tocados.

## Peças

| Peça | Papel |
|---|---|
| `resources/ragx-bundle/` (`extraResources`) | `uv.exe`, wheel do ragx, `bundle.json` (versões + SHA256). |
| `electron/bootstrap/bundle.ts` | Localiza o bundle e valida hashes antes de executar. |
| `electron/bootstrap/path-user.ts` | Garante `~\.local\bin` no PATH do usuário; grava `bootstrap-state.json` (`pathAdded`). |
| `electron/bootstrap/uninstall.ts` | Remove CLI, MCP, PATH (se `pathAdded`) e opcionalmente `~\.ragx`. |
| Job `ragx-install` + `Step.cmd: 'uv'` | `uv tool install --force --no-config --python 3.12 wheel[all]` (fallback sem extra), PATH, `ragx mcp install --client claude-code` se houver Claude Code. |
| `main.ts` | `--bootstrap` (headless, log em `%APPDATA%\RAGX Painel\bootstrap.log`, exit 0/1), `--uninstall-cli`, autoenfileira se `resolveRagx()` é `null`; depois `resetRagxCache()` + nova checagem. |
| `build/installer.nsh` | `customInstall` chama `--bootstrap`; `customUnInstall` mostra as duas caixas e chama `--uninstall-cli`. Sem lógica própria. |
| CLI Python | `ragx mcp uninstall --client <nome>`: remove só a chave `ragx`, preserva o resto, não mexe em config ilegível. |
| Card RAGX CLI | Ação "Instalar / Tentar de novo" (`ragx-install`). |

## Erros

Sem rede: job falha com as últimas linhas do `uv`; "Tentar de novo" idempotente.
`ragx.exe` travado (MCP aberto): mensagem manda fechar o Claude Code. Hash
divergente: aborta antes de executar. Antivírus (ENOENT/EPERM): mensagem própria.
Falha do bootstrap nunca falha a instalação: o painel refaz na primeira abertura.

## Limites

Hash em `bundle.json` protege contra corrupção, não adulteração (exige assinatura
de código). Desinstalar o painel sem a caixa da CLI deixa o `ragx`.

## Fora de escopo

macOS/Linux, Ollama embutido, instalar Claude Code, modo offline, assinatura de
código, auto-update.

## Testes

vitest (bundle, path-user, ragx-install, uninstall, checker pós-bootstrap),
pytest (`mcp uninstall`), smoke em `windows-latest` (instala `/S`, confere
`ragx --version`, desinstala com `--remove-cli`, confere PATH). Validação final
da UI com Playwright.
