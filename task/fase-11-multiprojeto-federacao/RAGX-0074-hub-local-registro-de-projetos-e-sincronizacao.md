# RAGX-0074 — Hub local: registro de projetos e sincronização

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0073`, `RAGX-0061` |
| **Bloqueia** | `RAGX-0075` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [adr/ADR-0009-tres-camadas-de-conhecimento.md](../../docs/adr/ADR-0009-tres-camadas-de-conhecimento.md) |
| **Status** | `todo` |

## Objetivo

Criar a base da máquina que agrega vários projetos, sem jamais ler o código-fonte de nenhum deles.

## Entregáveis

- [ ] `~/.ragx/hub/hub.db` com `projects`, `federation_items`, `cross_links`, `unresolved` e migrações próprias
- [ ] `~/.ragx/hub/registry.json`
- [ ] `ragx project register [PATH] [--name] [--visibility]` e `--from-federation FILE` (projeto NÃO clonado)
- [ ] `ragx project list` e `ragx project unregister`
- [ ] `ragx hub sync [--project]` incremental, por `manifest_hash` + `remote_hash` + `last_sync`
- [ ] `ragx hub status` com idade, estado (`ok`/`missing`/`stale`/`degraded`) e motivo da degradação
- [ ] **O hub lê apenas artefatos derivados** (`knowledge/`, `federation/`) e os re-escaneia na entrada
- [ ] `ragx hub reset`

## Fora de escopo

- Resolução de vínculos (RAGX-0075)
- Consulta cross-project (RAGX-0076)

## Critérios de aceite

- [ ] Teste arquitetural: `ragx.federation.hub` nunca lê o working tree de outro projeto
- [ ] Projeto registrado cujo caminho sumiu vira `missing`, não é removido
- [ ] Projeto só-federação funciona sem `path`
- [ ] `hub sync` reprocessa apenas o que mudou
- [ ] Modelos de embedding divergentes são detectados e o projeto é marcado `degraded` com motivo
- [ ] Projeto `private` não entra no hub
- [ ] Apagar o hub e ressincronizar reproduz o mesmo estado

## Testes

- [ ] 3 projetos sintéticos
- [ ] Teste arquitetural de leitura
- [ ] Teste de re-scan na entrada

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
