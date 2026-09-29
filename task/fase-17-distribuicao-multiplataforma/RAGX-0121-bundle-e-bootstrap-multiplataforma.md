# RAGX-0121: Bundle (`uv`) e bootstrap da CLI por plataforma

| | |
|---|---|
| **Fase** | 17: Distribuição do painel em Windows, Linux e macOS |
| **Prioridade** | P2 |
| **Estimativa** | ~2d |
| **Depende de** | RAGX-0119, RAGX-0120 |
| **Documentação** | [spec do instalador](../../docs/superpowers/specs/2026-09-23-instalador-completo-design.md) · [ADR-0016](../../docs/adr/ADR-0016-instalador-completo-do-painel.md) |
| **Status** | `todo` |

## Objetivo

Base comum para Linux e macOS: o pacote embutido e a instalação da CLI deixam de
ser só de Windows. Sem isso, os instaladores de RAGX-0122 e 0123 não têm como
entregar "RAGX CLI verde" sozinhos.

## Entregáveis

- [ ] `scripts/prepare-bundle.mjs` escolhe o `uv` pela plataforma e arquitetura (`x86_64-pc-windows-msvc`, `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, `x86_64-apple-darwin`, `aarch64-apple-darwin`), com SHA256 conferido como hoje
- [ ] Extração do arquivo sem depender do `tar` do Windows (`.tar.gz` em Linux e macOS)
- [ ] `bundle.json` e `electron/bootstrap/bundle.ts` cientes do nome do executável (`uv` sem `.exe`)
- [ ] `electron/bootstrap/path-user.ts`: garantir `~/.local/bin` no PATH em Linux e macOS (perfil do shell), sem `powershell.exe`
- [ ] `electron/bootstrap/uninstall.ts` sem suposição de Windows
- [ ] Bootstrap roda na primeira abertura do app quando `resolveRagx()` é `null` (o caminho que o painel já tem), já que não há NSIS fora do Windows
- [ ] Testes de unidade dos ramos novos, sem mock que esconda a plataforma

## Fora de escopo

- Empacotar `.dmg`, AppImage ou `.deb` (RAGX-0122 e 0123)
- Alterar o comportamento no Windows

## Critérios de aceite

- [ ] `npm run bundle` gera um pacote válido em Windows, Linux e macOS (a CI da RAGX-0119 prova)
- [ ] Um teste por plataforma cobre a escolha do `uv` e do executável
- [ ] O Windows continua idêntico: o smoke do `painel-windows` passa sem mudança

## Testes

vitest para a escolha de plataforma e para o PATH; smoke de bootstrap real em
Linux e macOS na CI (sem UI, via `--bootstrap`).

## Notas

Ao mexer no bootstrap, olhar o que a opção "um clique" adiada exige (ver README da
fase): a mesma rotina será a tela de preparação, então convém não amarrar nada ao
NSIS.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] `npm test`, `npm run lint`, `tsc` limpos
- [ ] CHANGELOG atualizado na MESMA alteração
