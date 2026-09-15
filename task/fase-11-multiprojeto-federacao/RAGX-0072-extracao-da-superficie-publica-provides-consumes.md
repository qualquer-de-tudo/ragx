# RAGX-0072 — Extração da superfície pública (provides / consumes)

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0034`, `RAGX-0069` |
| **Bloqueia** | `RAGX-0073` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [adr/ADR-0011-federacao-entre-projetos.md](../../docs/adr/ADR-0011-federacao-entre-projetos.md) |
| **Status** | `todo` |

## Objetivo

Derivar, do grafo referencial já existente, o que o projeto oferece ao mundo e o que ele consome de fora — a matéria-prima de toda a federação.

## Entregáveis

- [ ] `migrations/0008_federation.sql`: `federation_surface`
- [ ] `federation/surface.py`: extração de `provides` e `consumes` para http, event, package e table
- [ ] Detecção HTTP: definição de rota (Laravel, Express, FastAPI/Flask, Spring) e chamada de cliente HTTP
- [ ] Detecção de eventos: publicação e assinatura (nome do evento, classe, handler)
- [ ] Detecção de pacotes: dependências declaradas + pacotes publicados pelo próprio projeto
- [ ] `federation/normalize.py`: normalização de rota entre stacks (`{id}` · `:id` · `<int:id>` · `%s` → `{}`)
- [ ] `confidence` e `detected_by` em todo item
- [ ] `federation/manual.json`: declarações curadas à mão, que vencem o derivado

## Fora de escopo

- Geração da fatia em disco (RAGX-0073)
- Resolução entre projetos (RAGX-0075)

## Critérios de aceite

- [ ] Rotas equivalentes em Laravel, Express e FastAPI normalizam para a mesma forma
- [ ] Chamada HTTP com URL montada dinamicamente é reportada com confiança baixa, não inventada
- [ ] Item manual sobrescreve o derivado de mesmo `normalized`
- [ ] Projeto sem nenhuma superfície pública gera fatia vazia, não erro
- [ ] Extração roda sobre chunks já admitidos pelo gate — nunca sobre o arquivo bruto

## Testes

- [ ] Fixture por framework (Laravel, Express, FastAPI, Spring)
- [ ] Tabela de normalização de rotas

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
