# RAGX-0034 — Extrator referencial e catálogo de tecnologias (camada 2)

| | |
|---|---|
| **Fase** | 3 — Graph Knowledge |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0033` |
| **Bloqueia** | `RAGX-0035`, `RAGX-0043`, `RAGX-0072` |
| **Documentação** | [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` |

## Objetivo

Ligar entidades já existentes entre si e reconhecer tecnologias pela evidência mais confiável disponível: a dependência declarada.

## Entregáveis

- [ ] `graph/extractors/reference.py`: `calls`, `uses`, `documented_by`, `mentions`, `endpoint`, `table`
- [ ] `graph/extractors/technologies.yaml` — catálogo curado (nome, aliases, sinais)
- [ ] Leitura de `composer.json`, `package.json`, `pyproject.toml`, `go.mod` para tecnologias
- [ ] Regra dura: só cria aresta para entidade que JÁ existe (não inventa nó)

## Fora de escopo

- Inferência semântica (RAGX-0037)

## Critérios de aceite

- [ ] Tecnologia declarada como dependência é reconhecida com `confidence = 1.0`
- [ ] Menção em texto sem dependência declarada entra com confiança menor
- [ ] Nenhum nó órfão é criado por esta camada
- [ ] `documented_by` liga corretamente doc e entidade de código pelo heading

## Testes

- [ ] Fixture de projeto Laravel e de projeto Node com dependências reais

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
