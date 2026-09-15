# RAGX-0037 — Extrator semântico opt-in (camada 3)

| | |
|---|---|
| **Fase** | 3 — Graph Knowledge |
| **Prioridade** | P2 — média |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0036` |
| **Bloqueia** | — |
| **Documentação** | [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` |

## Objetivo

Enriquecer o grafo com conceitos e dependências de domínio, sem abrir mão de rastreabilidade nem de controle de custo.

## Entregáveis

- [ ] `graph/extractors/semantic.py`, acionado apenas por `--semantic`
- [ ] Saída validada por schema Pydantic; item fora do schema é descartado
- [ ] Toda entidade precisa de âncora em pelo menos um `chunk_id`, senão é rejeitada
- [ ] `source = "semantic"`, `confidence < 1.0`
- [ ] Respeita `security.allow_remote_llm` (padrão `false`)
- [ ] Entrada limitada a chunks já admitidos pelo gate

## Fora de escopo

- Habilitar por padrão — é e continua opt-in

## Critérios de aceite

- [ ] Desabilitado por padrão; camadas 1-2 funcionam sem nenhum LLM
- [ ] Entidade sem âncora nunca é gravada
- [ ] Reconstrução preserva entidades semânticas, refazendo só as estruturais
- [ ] Custo estimado (tokens/chamadas) é reportado antes de executar

## Testes

- [ ] Cliente LLM fake devolvendo JSON válido, inválido e sem âncora

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
