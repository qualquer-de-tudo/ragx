# 19 — Watch e autonomia do agente

> Como o índice acompanha o código sozinho, e o que o agente pode fazer com ele.
> Ver [ADR-0012](adr/ADR-0012-poder-do-agente-sobre-o-indice.md).

## O problema que os dois resolvem

Um índice desatualizado não dá erro. Ele responde — com confiança — sobre
código que não existe mais. É a pior falha possível num sistema de
conhecimento, porque ninguém percebe.

Duas frentes atacam isso:

- **`ragx watch`** — o índice se atualiza sozinho enquanto você edita
- **escrita via MCP** — o agente garante frescor antes de raciocinar

---

## `ragx watch`

```bash
ragx watch
```

```
ragx watch  E:\RAGPAG\ragx
  varredura a cada 2s · debounce 1.5s · consolida a cada 25 mudanças
  Ctrl+C para sair

  ~ src/ragx/search/hybrid.py
  ✓ 1 arquivo(s) reindexado(s)

  ciclos 43 · reindexações 6 · consolidações 0 · documentos 8
```

### Por polling, não por API do sistema

Decisão deliberada, por três motivos:

1. **Zero dependência nova.** `watchdog` traria uma árvore de pacotes e um
   backend diferente por plataforma.
2. **Mesmo sinal do indexador.** `size+mtime` é exatamente o que o pipeline
   incremental usa para decidir o que reprocessar. Watcher e indexador nunca
   discordam sobre o que mudou.
3. **Editor moderno confunde API nativa.** Salvar via arquivo temporário +
   rename gera uma sequência de eventos difícil de interpretar. `stat` mostra
   só o resultado final.

O custo é um `stat` por arquivo não ignorado, por ciclo. No RAGX (301
documentos, ~12 mil arquivos ignorados antes de qualquer I/O), milissegundos.

### Duas velocidades

| Evento | O que roda | Custo |
|---|---|---|
| a cada mudança (após o debounce) | `index` incremental | ~centenas de ms |
| a cada `full_sync_every` mudanças | `sync` completo — grafo, dicionário, `knowledge/` | segundos |

Consolidar a cada Ctrl+S seria caro demais; nunca consolidar deixaria o grafo
e o dicionário — que são a primeira coisa que o agente lê — permanentemente
atrás.

### Debounce

Salvar 12 arquivos em sequência produz **uma** reindexação, não doze. O relógio
reinicia a cada mudança detectada; a reindexação só acontece depois de
`debounce_s` de quietude.

### Configuração

```toml
[watch]
enabled = true
interval_s = 2.0        # entre varreduras
debounce_s = 1.5        # quietude antes de aplicar
full_sync_every = 25    # mudanças até consolidar
max_batch = 500
```

Flags equivalentes: `--interval`, `--debounce`, `--consolidate-every`.

### Uma passada só

```bash
ragx watch --once          # aplica o pendente e sai
ragx watch --once --plain  # saída JSON, para CI e hook de Git
```

### Falha nunca derruba o laço

Um watcher que morre no primeiro arquivo malformado é pior que nenhum watcher:
o agente segue consultando um índice parado sem ninguém perceber. Erro de
indexação vira `last_error` no painel, e o laço continua.

---

## Escrita via MCP

O agente controla o índice. **Não** controla o filesystem, e **não** controla o
Security Gate.

```bash
ragx mcp serve              # escrita LIGADA (padrão)
ragx mcp serve --read-only  # só consulta
```

### Ferramentas

| Ferramenta | Quando o agente usa | Custo |
|---|---|---|
| `get_playbook` | uma vez, no início da sessão | trivial |
| `refresh` | no início de cada tarefa | barato quando nada mudou |
| `reindex` | varredura explícita; `full=true` só se o chunker mudou | médio |
| `sync` | depois de mudança estrutural (merge grande, arquivos movidos) | caro |
| `rebuild_graph` | grafo atrás do código | médio |
| `generate_dictionary` | dicionário atrás do grafo | barato |
| `base_sync` | falta conhecimento base declarado | rede |
| `publish_contract` | superfície pública mudou | barato |

### O que continua impossível

- ler um arquivo do filesystem
- obter conteúdo de arquivo bloqueado pelo gate
- indexar fora da raiz do projeto
- executar comando arbitrário
- escolher a origem de uma fonte base (vem de arquivo versionado, revisado por
  humano)

A fronteira do [ADR-0006](adr/ADR-0006-mcp-casca-fina.md) nunca foi "o agente
não pode fazer nada". É **que caminho o byte percorre** — e esse caminho não
mudou:

```
disco -> iter_files -> SecurityGate.admit -> parser -> store -> agente
```

`reindex` faz o índice percorrer esse caminho de novo. Não cria um atalho.

### `get_playbook`

Dar poder sem dizer como usá-lo produz o pior resultado: um agente que pode
reindexar o repositório inteiro e faz isso a cada pergunta.

`get_playbook` devolve o procedimento operacional — ordem das ferramentas,
quando reindexar, o que o índice deliberadamente não faz. Vive em Python
(`ragx/mcp/playbook.py`), não num `.md`: um playbook lido do disco abriria
exatamente o buraco que o resto do módulo fecha.

### Modo leitura mostra as ferramentas mesmo assim

Ferramenta ausente faz o agente concluir que a operação não existe e inventar
um contorno. Ferramenta que responde `write_disabled` com a instrução de como
habilitar diz a verdade. Há teste garantindo que elas continuam listadas.

---

## Watch ou MCP?

Não é escolha — os dois cobrem buracos diferentes.

| | `ragx watch` | escrita via MCP |
|---|---|---|
| Quem dispara | mudança no disco | o agente |
| Cobre edição feita fora do agente | **sim** | não |
| Cobre `git pull`, merge, rebase | sim (como mudança em massa) | sim (`sync`) |
| Exige processo rodando | sim | não |
| Reconstrói grafo sob demanda | só na consolidação | sim |

Na prática: deixe `ragx watch` rodando durante o desenvolvimento e mantenha
`refresh` no início de cada tarefa do agente. O segundo é o cinto de segurança
do primeiro.

## Ver também

- [09 — MCP](09-mcp.md)
- [18 — Conhecimento base](18-conhecimento-base.md)
- [ADR-0012](adr/ADR-0012-poder-do-agente-sobre-o-indice.md)
- [ADR-0006](adr/ADR-0006-mcp-casca-fina.md)
