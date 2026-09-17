# RAGX-0103 — Trocar o modelo de embedding para retrieval assimétrico

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 3 — braço semântico |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0097` · `RAGX-0099` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `todo` |

## Objetivo

O modelo configurado é `paraphrase-multilingual-MiniLM-L12-v2`: um modelo de PARÁFRASE, treinado para dizer se duas frases significam o mesmo. Busca é **assimétrica** — pergunta curta contra trecho longo de código. **Já medido:** trocar para `nomic-embed-text-v1.5` leva o híbrido de 0,62 para **0,77** de recall@5 e de 0,51 para **0,58** de MRR, com o keyword inalterado como controle.

## Entregáveis

- [ ] `nomic-ai/nomic-embed-text-v1.5` como default do provider `fastembed`
- [ ] `[embedding] batch` reduzido no default para modelo de janela grande — `batch=32` estoura memória (15,3 GB num lote); `batch=4` funciona
- [ ] Teto de tokens por chunk na entrada do embedder, para que um chunk gigante não derrube o lote
- [ ] Mensagem de erro acionável quando o ONNX aborta por memória — hoje sai um traceback de alocação
- [ ] Caminho de migração: `ragx reindex --embed-only` detecta troca de modelo e reembute
- [ ] Documentar o custo: índice dobra de tamanho (768 contra 384 dimensões)

## Fora de escopo

- Avaliar `jina-embeddings-v2-base-code` e `multilingual-e5-large` (fica como tarefa futura)
- Mudar o provider `ollama`, que já usa um modelo assimétrico

## Critérios de aceite

- [ ] Ganho de MRR confirmado no conjunto ampliado (`RAGX-0099`) — com n=26 é promissor, não conclusivo
- [ ] `ragx index` completa sem estourar memória numa máquina com 16 GB
- [ ] Tempo de indexação completa medido e publicado
- [ ] Tamanho final do índice medido e comparado ao orçamento de `docs/16`
- [ ] Projeto já indexado com o modelo antigo continua funcionando até reembutir

## Testes

- [ ] Teste de que a troca de modelo invalida os vetores antigos (já existe; confirmar)
- [ ] Teste de que um chunk acima do teto é truncado ou pulado, sem derrubar o lote
- [ ] Benchmark de indexação registrado

## Notas

Medição completa na seção 3.5.1 da auditoria:

```text
                    recall@5    MRR   nDCG@10
MiniLM   keyword        0,77   0,47      0,76
         semantic       0,54   0,44      0,66
         hybrid         0,62   0,51      0,76
nomic    keyword        0,77   0,47      0,76   <- controle idêntico
         semantic       0,62   0,47      0,81
         hybrid         0,77   0,58      0,87
```

**Cite o MRR, não o nDCG** — o nDCG está medido com o instrumento quebrado da `RAGX-0098`.

Efeito colateral bom: o nomic é treinado com Matryoshka, então a truncagem 768 → 256 do estágio grosseiro passa a ser legítima. Hoje ela funciona por sorte.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
