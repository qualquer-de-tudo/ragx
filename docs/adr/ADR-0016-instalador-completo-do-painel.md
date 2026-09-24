# ADR-0016 — O `.exe` do painel instala a CLI; a lógica fica em TypeScript

- **Status:** aceito
- **Data:** 2026-09-23
- **Contexto:** Fase 16 — Instalador completo do painel (Windows)
- **Relacionado:** [ADR-0007](ADR-0007-nome-do-binario.md), [ADR-0006](ADR-0006-mcp-casca-fina.md), [spec](../superpowers/specs/2026-09-23-instalador-completo-design.md)

## Contexto

O `RAGX Painel Setup.exe` (NSIS) instalava só o Electron. A CLI `ragx`, o `uv`,
o PATH e o registro do MCP vinham do `install/install.ps1`, que o usuário final
do painel não roda. Resultado: logo após instalar, o passo 2 do assistente
mostrava RAGX CLI, Claude Code e Ollama como "Não conectado".

## Decisão

1. **O `.exe` carrega o necessário e o NSIS só dispara.** `extraResources`
   embute `uv.exe`, o wheel do RAGX e um `bundle.json` com versões e SHA256.
   O `uv` vem de uma versão fixa, com o `.sha256` publicado conferido no build.
   O hook `customInstall` executa `RAGX Painel.exe --bootstrap`.
2. **Uma única implementação, em TypeScript.** `--bootstrap`, o botão
   "Instalar / Tentar de novo" do card RAGX CLI e `--uninstall-cli` usam o mesmo
   código (`electron/bootstrap/`), testável com vitest. O `installer.nsh` não
   tem lógica: só chama o painel.
3. **Internet é permitida na instalação.** O `uv` baixa o Python 3.12 e as
   dependências (`uv tool install --python 3.12 wheel[all]`).
4. **Falha do bootstrap nunca falha a instalação.** No modo interativo o NSIS
   avisa; em `/S` fica em silêncio. O painel refaz na primeira abertura.
5. **Desinstalador com duas escolhas independentes:** remover a CLI e o
   registro no Claude Code (padrão Sim) e remover os dados do hub `~\.ragx`
   (padrão Não). Em `/S`, `--remove-cli` e `--remove-data`. Ollama e os
   `.ragx/` dos projetos nunca são tocados. Atualização por cima não remove nada.
6. **O hook de desinstalação é `customRemoveFiles`.** No template do
   electron-builder 25.x, `customUnInstall` roda **depois** de
   `RMDir /r $INSTDIR`, quando o `.exe` do painel já foi apagado.
   `customRemoveFiles` roda antes, mas substitui a remoção padrão; por isso o
   `installer.nsh` repete esse bloco do template. Ao atualizar o
   electron-builder, conferir `templates/nsis/uninstaller.nsh`.
7. **A release passa a anexar o instalador**, e o job `painel-windows` o testa
   de ponta a ponta em `windows-latest` (instala `/S`, `ragx --version`,
   `ragx mcp serve --help`, desinstala com `--remove-cli`, confere que o
   `ragx.exe` sumiu).

## Consequências

**Positivas**

- Só com o `.exe`, numa máquina limpa e com internet, o usuário chega a "RAGX
  CLI verde".
- Instalar e reparar são o mesmo código; não há um segundo instalador para
  manter em sincronia com o `install.ps1`.
- Desinstalar deixa a máquina como estava, se o usuário pedir.

**Negativas aceitas**

- O `.exe` cresce (~40 MB de `uv.exe` mais o wheel).
- O SHA256 do `bundle.json` protege contra corrupção, não contra adulteração;
  isso exige assinatura de código, hoje fora de escopo.
- O bloco padrão de remoção repetido no `installer.nsh` acompanha o template
  do electron-builder.
- Desinstalar sem marcar a CLI deixa o `ragx` instalado.

## Alternativas descartadas

**Chamar `install.ps1` a partir do NSIS.** Duplica a lógica em outra
linguagem, sem teste unitário, e o script depende de política de execução.

**Embutir Python inteiro no `.exe`.** Inflaria o instalador e deixaria de usar
o gerenciamento de versões do `uv`.

**Lógica de instalação e remoção em NSIS.** Difícil de testar, e a rotina de
"Reparar" do painel teria de ser reescrita.
