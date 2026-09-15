# ADR-0004 — Ollama `nomic-embed-text` como provider padrão

**Status:** aceito · 2026-09-15

## Contexto

O RAGX precisa gerar embeddings de milhares de chunks, e há um requisito de
segurança que restringe fortemente as opções: **o conteúdo do projeto não deve sair
da máquina**. Um embedder remoto transformaria cada indexação em um upload do
código-fonte para um terceiro — exatamente o risco que o Security Gate existe para
evitar.

Contexto local relevante: já existe um `nomic-embed-text` baixado em
`E:\RAGPAG\ragpag\ollama_models` (~262 MB), o que elimina o custo de setup inicial.

## Decisão

Provider abstrato com três implementações:

```python
class Embedder(Protocol):
    id: str            # "ollama:nomic-embed-text"
    dim: int
    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...
```

| Provider | Modelo | Dim | Uso |
|----------|--------|-----|-----|
| `ollama` (**padrão**) | `nomic-embed-text` | 768 | desenvolvimento e produção local |
| `fastembed` | `paraphrase-multilingual-MiniLM-L12-v2` | 384 | **máquinas sem Ollama** e CI |
| `hashing` | — | 256 | testes de pipeline (qualidade semântica nula) |

Detalhes de implementação que são obrigatórios, não opcionais:

1. **Prefixos de tarefa.** `nomic-embed-text` foi treinado com prefixos assimétricos:
   `search_document: ` para conteúdo e `search_query: ` para consulta. Sem eles, a
   qualidade cai visivelmente. A responsabilidade é do provider, nunca do chamador —
   por isso a interface tem dois métodos e não um.
2. **Normalização L2 na gravação**, viabilizando o produto escalar do ADR-0003.
3. **Batch** de 32 por requisição, com retry exponencial em erro de rede.
4. **Cache por `content_hash`** em `.ragx/cache/emb/<model_id>/`, o que faz chunk
   movido ou arquivo renomeado não custar nada.
5. **Degradação explícita**: embedder indisponível não derruba a indexação — os
   chunks são gravados sem vetor, a busca cai para keyword e um aviso claro é
   emitido. `ragx index --embed-only` completa depois.
6. `dim` do provider é validado contra `embedding_models.dim` na abertura do banco.
   Divergência é erro, não aviso.

## Consequências

Positivas:
- Nenhum byte do projeto sai da máquina no fluxo padrão.
- Sem custo por token.
- Modelo já disponível localmente.
- `nomic-embed-text` aceita 8192 tokens de contexto — chunk grande não é truncado.

Negativas:
- Exige o daemon Ollama rodando. Mitigação: `fastembed` como fallback sem daemon e
  `ragx doctor` com instrução acionável.
- Qualidade multilíngue inferior a modelos maiores (`bge-m3`, `multilingual-e5-large`).
  Mitigação: modelo é configurável; a documentação registra `bge-m3` como upgrade
  recomendado para bases majoritariamente em português.
- Trocar de modelo invalida todos os vetores — fluxo de migração documentado em
  [15 — Configuração](../15-configuracao.md).

## Alternativas rejeitadas

- **OpenAI / Voyage / Cohere embeddings** — melhor qualidade, mas violam o requisito
  de não enviar código para fora e introduzem custo por indexação. Ficam disponíveis
  como provider opt-in, nunca como padrão.
- **sentence-transformers direto** — puxa PyTorch (~2 GB) como dependência.
  `fastembed` entrega o mesmo modelo por ONNX Runtime em ~220 MB.
- **TF-IDF / BM25 apenas** — é justamente o que a Fase 2 precisa superar.

## Adendo — quando NÃO há Ollama

Ollama exige instalar e manter um daemon. Onde isso não é possível (máquina
corporativa travada, CI, contêiner mínimo), `fastembed` é a escolha: ONNX
Runtime embarcado, modelo baixado **uma vez** e cacheado em
`.ragx/cache/models/`, offline a partir daí. Nenhum processo extra.

O default do fastembed é **multilíngue** de propósito: o corpus típico do RAGX
é documentação em português misturada com código, e um modelo só-inglês
perderia metade do sinal.

```bash
uv pip install "ragx[embed]"
ragx config set embedding.provider fastembed
ragx index . --embed-only
```

| | Ollama | fastembed |
|---|---|---|
| daemon | sim | **não** |
| download | modelo (~262 MB) | modelo (~220 MB) |
| offline depois | sim | sim |
| dim padrão | 768 | 384 |
| multilíngue | parcial | **sim** |
