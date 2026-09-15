# ADR-0008 — Security Gate antes do parser, não depois do índice

**Status:** aceito · 2026-09-15

## Contexto

Há duas formas de impedir que segredos vazem por um RAG:

**(A) Filtrar na saída.** Indexa tudo e remove o que for sensível na hora de
responder. É o caminho mais fácil de implementar e o modelo de segurança mais fraco
que existe, porque o segredo passa a existir em N lugares:

```text
chunks no SQLite · cache de embeddings · vetor enviado ao embedder ·
logs de indexação · nós de grafo · dictionary.json versionado no Git ·
pacote .rag compartilhado · backups
```

Basta **um** desses caminhos esquecer o filtro para o segredo vazar. E cada feature
nova cria um novo caminho a lembrar.

**(B) Filtrar na entrada.** O conteúdo sensível nunca chega a existir no sistema.
Só há um lugar onde acertar.

## Decisão

O `SecurityGate` fica **entre o leitor de arquivos e o parser**. Nenhum componente
fora de `ragx.security` recebe bytes que não tenham passado por `gate.admit()`.

```text
FileWalker → IgnoreEngine → SecurityGate → Parser → Chunker → Embedder → Store
                                 ▲
                      última fronteira: depois daqui,
                      o conteúdo é considerado limpo
```

Consequências de design que decorrem disso:

1. O gate é construído na **Fase 0**, antes de qualquer indexação existir.
2. Os testes das cinco superfícies são escritos na Fase 0 com `xfail` para as fases
   futuras; cada fase posterior tem como *definition of done* virar seu `xfail`
   em `pass`. Segurança não é retroativa.
3. `redact` acontece **antes** do chunking — chunk nenhum contém o valor original,
   nem em memória depois do gate.
4. O gate roda de novo no export (Fase 8), porque o ruleset pode ter evoluído desde
   a indexação. Defesa em profundidade não contradiz o princípio; complementa.
5. Teste arquitetural garante que só `walker.py` e `sync/incremental.py` leem o
   filesystem do projeto.

## Consequências

Positivas:
- Uma superfície de proteção, não N.
- Garantia composicional: qualquer feature futura que consuma o store herda a
  proteção automaticamente, sem precisar lembrar de nada.
- Auditoria simples: "o segredo está no banco?" é uma query, e a resposta é sempre não.
- Segredo não trafega para o provedor de embedding, nem mesmo local.

Negativas:
- Falso positivo bloqueia conteúdo legítimo. Mitigações: allowlist de placeholders,
  ajuste de severidade por contexto de arquivo, `.ragignore`, e `ragx security scan`
  para inspeção antes de indexar. O teste de "ausência de falso negativo"
  (`.env.example` e código legítimo **precisam** ser indexados) existe justamente
  para impedir que o gate vire um bloqueador indiscriminado.
- Custo de scan em toda indexação. Medido: regex compilado uma vez, ~50 regras,
  custo desprezível frente ao parsing.
- Arquivo que vira sensível depois exige reindexação para ser removido. Coberto
  pelo re-scan do `ragx sync`.

## Alternativas rejeitadas

- **Filtro na saída (A)** — descrito acima.
- **Criptografar o índice** — protege contra roubo do arquivo, não contra o agente
  que legitimamente consulta o índice e recebe o segredo em texto claro.
- **Confiar no `.gitignore`** — `.gitignore` é heurística de ruído, não política de
  segurança. Um `.env` não listado continua sendo um `.env`.
