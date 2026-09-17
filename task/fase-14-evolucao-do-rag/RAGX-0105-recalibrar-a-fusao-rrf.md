# RAGX-0105 — Recalibrar a fusão RRF

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 3 — braço semântico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0099` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [05-busca.md](../../docs/05-busca.md) |
| **Status** | `todo` |

## Objetivo

O default `weight_semantic=1,0 / weight_keyword=0,8` é o **pior ponto medido** da varredura (0,62). `1,0/1,0` dá 0,69. E os pesos são um controle fraco: de 0,3 a 1,0 o resultado não muda, porque RRF pontua por POSIÇÃO. O controle forte é o `rrf_k` (k=10 → 0,69 contra k=60 → 0,62).

## Entregáveis

- [ ] Varredura de `rrf_k` e pesos no conjunto ampliado, com os números registrados
- [ ] Defaults atualizados para o melhor ponto medido
- [ ] `docs/05-busca.md` explica que os pesos são controle fraco e o `rrf_k` é o forte — hoje o documento só descreve os pesos
- [ ] `candidate_factor` revisto: satura em 3, então o default atual está certo e isso merece ficar escrito

## Fora de escopo

- Trocar RRF por outra fusão — a justificativa de `docs/05-busca.md` continua válida
- Calibração automática por projeto

## Critérios de aceite

- [ ] Os defaults novos batem o `1,0/0,8` atual no conjunto ampliado
- [ ] A varredura é reexecutável por um script versionado, não um experimento perdido

## Testes

- [ ] Teste de que os defaults de `SearchCfg` são os do último resultado publicado

## Notas

Fazer DEPOIS da `RAGX-0103`: trocar o modelo muda qual braço merece mais peso, e calibrar antes seria calibrar para o modelo que vai sair.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
