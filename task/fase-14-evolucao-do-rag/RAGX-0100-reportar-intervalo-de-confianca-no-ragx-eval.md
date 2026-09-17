# RAGX-0100 — Reportar intervalo de confiança no ragx eval

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 1 — instrumento e caminho quente |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0098` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) |
| **Status** | `todo` |

## Objetivo

Enquanto a métrica aparecer sozinha, ela vai ser lida como precisa. Foi assim que '0,65 contra 0,77' virou a afirmação publicada de que a busca híbrida falhou o critério — quando são 4 consultas de diferença, dentro do ruído.

## Entregáveis

- [ ] `ragx eval` imprime `0,77 [0,58–0,89] n=26` em vez de `0,77`
- [ ] Intervalo de Wilson (correto para proporção com n pequeno), não o normal
- [ ] `--json` inclui `ci_low`, `ci_high`, `n`
- [ ] Aviso explícito quando a largura do IC passa de 0,20: o resultado não distingue os modos

## Fora de escopo

- Mudar como as métricas são calculadas (é a `RAGX-0098`)
- Testes estatísticos de significância entre modos — o IC já comunica o essencial

## Critérios de aceite

- [ ] A saída mostra o intervalo junto de cada métrica
- [ ] Com n=26 o aviso de largura aparece; com n≥150 não aparece
- [ ] MRR e nDCG, que são médias contínuas, usam erro-padrão em vez de Wilson

## Testes

- [ ] Teste do cálculo de Wilson contra valores conhecidos
- [ ] Teste de que o aviso aparece e some conforme o n

## Notas

MRR é o indicador mais limpo do conjunto: usa a posição do primeiro acerto e não é inflado pelo defeito de caminhos duplicados. Vale dizer isso na saída.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
