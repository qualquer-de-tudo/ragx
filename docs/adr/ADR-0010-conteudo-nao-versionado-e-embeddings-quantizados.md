# ADR-0010 — Conteúdo de chunk não versionado; embeddings versionados quantizados

**Status:** aceito · 2026-09-15

## Contexto

O conhecimento versionado tem teto duro (ver [16 — Orçamento de tamanho](../16-orcamento-de-tamanho.md)).
Medindo os componentes, por chunk:

| Componente | Bytes/chunk | 100k chunks |
|------------|-------------|-------------|
| Metadados do chunk | ~180 | 17 MB |
| **Conteúdo do chunk** | ~900 | **86 MB** |
| **Embedding float32 @ 768d** | 3.072 | **293 MB** |
| Embedding int8 @ 768d | 768 | 73 MB |
| Embedding int8 @ 256d | 256 | 24 MB |

Versionando conteúdo e float32: **396 MB** com 100k chunks — e, como o Git guarda
histórico, esse custo se repete a cada reindexação que mexa nos arquivos.

## Decisão

### 1. Conteúdo de chunk não é versionado

Para o repositório do próprio projeto, o conteúdo do chunk é redundante: é uma fatia
de um arquivo que já está versionado, em caminho e intervalo de linhas conhecidos.

`knowledge/chunks/*.jsonl` guarda `rel_path`, `[start_line, end_line]`, `symbol`,
`kind`, `content_hash`, `token_count`, `parent` — e **não** `content`.

Reidratação no `ragx sync`:

```text
rel_path + [start, end] → lê do working tree → confere content_hash
   bate          → chunk reconstruído, embedding versionado reaproveitado
   não bate      → chunk re-derivado do arquivo (o arquivo mudou)
   arquivo sumiu → chunk descartado e reportado
```

A conferência de hash é o que torna a reidratação segura: divergência é detectada,
nunca silenciosa.

**Exceção deliberada:** `knowledge/federation/` guarda conteúdo **por valor**, porque
precisa funcionar sem o repositório de origem clonado. São poucos KB (ver
[ADR-0011](ADR-0011-federacao-entre-projetos.md)).

### 2. Embeddings versionados são int8 @ 256 dimensões

`nomic-embed-text` é treinado com Matryoshka, então truncar 768 → 256 dimensões
preserva a maior parte do sinal. Sobre a truncagem aplica-se quantização escalar
int8 por vetor, com `scale` e `offset` gravados junto.

Busca em dois estágios:

```text
[1] busca grosseira em int8@256      top-100
[2] rescoring com float32@768 local  top-10    ← pulado se não houver vetor local
```

Logo após um `clone`, só o estágio 1 existe: a busca funciona com qualidade
ligeiramente menor, sem embedder e sem rede. `ragx sync` regenera os vetores completos
em `.ragx/` quando houver embedder disponível.

`[embedding] versioned_dim` e `versioned_quant` são configuráveis; `0`/`none`
desliga o versionamento de embeddings para quem preferir sempre regerar.

## Consequências

Positivas:
- 100k chunks passam de 396 MB para **~42 MB** versionados.
- Diff estável: mudar um arquivo altera os artefatos daquele documento e **1 shard**
  de embeddings entre 16 — o histórico do Git cresce pouco.
- Onboarding funciona offline: `git clone && ragx search` já responde.
- O conteúdo deixa de existir em dois lugares, então não há como divergir.

Negativas:
- Reidratação depende do working tree coerente. Mitigação: verificação por hash e
  relatório de divergência.
- Qualidade da busca cai um pouco sem os vetores locais. Medida no `ragx eval`, que
  passa a reportar as duas condições (`int8-only` e `com rescoring`), e a diferença
  é um número publicado, não uma suposição.
- Quantização é uma etapa a mais no pipeline de indexação. Custo desprezível
  (operação vetorizada em NumPy).
- Histórico antigo do Git não reidrata: um `knowledge/` de 6 meses atrás aponta para
  linhas que mudaram. Aceitável — conhecimento é derivado do presente, não do passado.

## Alternativas rejeitadas

- **Versionar conteúdo + float32** — 396 MB e crescendo. É o que o requisito proíbe.
- **Git LFS para os embeddings** — resolve tamanho, não resolve diff nem revisão, e
  exige LFS em todo clone.
- **Não versionar embedding nenhum** (proposta original da Fase 9) — obrigaria todo
  dev a ter Ollama rodando antes da primeira busca. Versionar int8 custa 24 MB e
  elimina esse pré-requisito.
- **Quantização binária (1 bit)** — 9,6 MB para 100k chunks, ainda menor, mas a perda
  de recall no estágio grosseiro é grande demais para ser a única representação
  disponível após um clone.
