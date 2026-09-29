# RAGX-0119: CI do painel (vitest, eslint, tsc) em Windows, Linux e macOS

| | |
|---|---|
| **Fase** | 17: Distribuição do painel em Windows, Linux e macOS |
| **Prioridade** | P1 |
| **Estimativa** | 0,5d |
| **Depende de** | nenhuma |
| **Documentação** | [src/app/README.md](../../src/app/README.md#testes-e-checagens) · [AGENTS.md](../../AGENTS.md) |
| **Status** | `todo` |

## Objetivo

Hoje os 796 testes do painel, o eslint e o `tsc` só rodam na máquina de quem
mexe. O `AGENTS.md` trata bug de caminho ou de encoding que aparece em uma só
plataforma como coisa séria, e o painel é o único componente sem essa rede.

## Entregáveis

- [ ] Job `painel` em `.github/workflows/ci.yml`, matriz `ubuntu-latest`, `windows-latest`, `macos-latest`
- [ ] Passos: `npm ci`, `npm run lint`, `npx tsc -p tsconfig.app.json --noEmit`, `npx tsc -p tsconfig.electron.json --noEmit`, `npm test`
- [ ] Cache do npm (`actions/setup-node` com `cache: npm` e `cache-dependency-path: src/app/package-lock.json`)
- [ ] Testes que falharem só em um sistema corrigidos na origem (caminho, separador, fim de linha, `.exe`), não ignorados
- [ ] CHANGELOG (item de CI/manutenção)

## Fora de escopo

- Gerar instalador (é da RAGX-0120, 0122 e 0123)
- Testes de interface com Playwright na CI

## Critérios de aceite

- [ ] O job roda em PR e em push na `main` nos três sistemas e passa
- [ ] Um teste quebrado de propósito em uma plataforma derruba o job (prova de que ele é bloqueante)
- [ ] Tempo do job por sistema abaixo de 5 min com cache

## Testes

Os próprios testes do painel; o que se entrega aqui é o job.

## Notas

Provável que apareçam falhas no Linux e no macOS nos testes que assumem Windows
(`ragx.exe`, `\`, `%APPDATA%`). Cada uma vira correção pequena nesta tarefa. Se
alguma exigir redesenho, para e vira tarefa própria, como manda o `README.md` do board.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] `npm test`, `npm run lint` e `tsc` limpos nos três sistemas na CI
- [ ] CHANGELOG atualizado na MESMA alteração
