# ADR-0003 — Busca vetorial por força bruta até 100k chunks

**Status:** aceito · 2026-09-15

## Contexto

Busca semântica precisa encontrar os K vetores mais próximos da query. Índices
aproximados (HNSW, IVF) existem para escala grande, mas trazem custo: dependência
nativa, parâmetros a calibrar (`M`, `ef_construction`, `nprobe`), reconstrução do
índice a cada lote de inserções e — o ponto que mais importa aqui — **recall < 100%**,
o que torna testes de qualidade não determinísticos.

Dimensionamento do caso real: um repositório de ~5.000 arquivos gera ~15.000 chunks.

```text
15.000 × 768 dims × 4 bytes  =  46 MB
100.000 × 768 × 4            = 307 MB
200.000 × 768 × 4            = 614 MB
```

Um produto escalar de 15.000 × 768 em NumPy leva poucos milissegundos.

## Decisão

1. **Até 100.000 chunks:** força bruta com NumPy. Vetores gravados normalizados
   (L2 = 1), então cosseno = produto escalar. Matriz carregada uma vez por processo
   e cacheada, invalidada pelo `index_runs.id` mais recente.

2. **Acima de 100.000 chunks:** `ragx doctor` e `ragx status` emitem aviso recomendando
   o índice aproximado. A implementação fica atrás do Protocol `VectorIndex`, então
   trocar não toca em nada da camada de busca.

```python
class VectorIndex(Protocol):
    def add(self, chunk_ids: Sequence[str], vectors: np.ndarray) -> None: ...
    def search(self, query: np.ndarray, k: int, mask: np.ndarray | None = None) -> list[tuple[str, float]]: ...
    def remove(self, chunk_ids: Sequence[str]) -> None: ...
```

3. **Caminho de upgrade:** `sqlite-vec` primeiro (mantém "um arquivo"); `hnswlib`
   como segunda opção se a latência exigir.

## Consequências

Positivas:
- Recall exato: 100%. Avaliação de qualidade mede a busca, não o índice.
- Zero dependência nativa, zero parâmetro a calibrar.
- Filtro combinado é trivial: máscara booleana NumPy aplicada **antes** do top-K,
  o que evita o problema clássico de filtro pós-ANN devolver menos resultados que
  o pedido.
- Inserção é `append` — nada a reconstruir.

Negativas:
- Memória proporcional ao corpus. Mitigado pelo limiar e pelo aviso automático.
- Latência cresce linearmente. Aceitável até o limiar definido.

## Alternativas rejeitadas

- **HNSW desde o início** — otimização prematura; complica testes de qualidade por
  causa do recall aproximado.
- **FAISS** — pesado (centenas de MB), overkill para o alvo.
- **Busca vetorial em SQL puro** — `sqlite3` não tem operações vetoriais; iterar
  linha a linha em Python seria ordens de magnitude mais lento que NumPy.
