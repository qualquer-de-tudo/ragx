# RAGX-0206 — Scan de segurança que cabe no painel

| | |
|---|---|
| **Fase** | 25 — Economia real |
| **Prioridade** | P1 |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [14-cli.md](../../docs/14-cli.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `review` |

## Objetivo

No cartão Segurança do projeto, "Atualizar achados de segurança" falhava com `excedeu o tempo limite de 60s` nos
projetos grandes: a varredura completa abre e lê todos os arquivos e leva **4 min 5 s** no Juriflux (17.917
arquivos). O `--staged`, que devia ser quase instantâneo, gastava 10,9 s listando a árvore inteira para só então
filtrar.

## Entregáveis

- [x] `ragx security scan --cached`: arquivo com `size`+`mtime` iguais aos do índice e contexto do veredito igual
      não é reaberto; achado volta dos `security_events` do índice; o que mudou, é novo ou ficou sem evento é lido
- [x] Sem índice, ou com o contexto do veredito diferente, volta para a varredura completa; JSON com `mode` e `reused`
- [x] `--staged` examina só os arquivos do stage (`iter_paths`); se o git falhar, varre tudo (nunca "nada")
- [x] Painel usa `--cached` com 3 min de limite e diz quantos arquivos não foram relidos e como reler tudo
- [x] Testes de equivalência entre o modo com cache e a varredura completa (depois de indexar, arquivo novo, alterado,
      apagado, regra mudada, sem índice, eventos apagados) e do `--staged`

## Fora de escopo

- Mudar o padrão da CLI: sem `--cached`, a varredura continua lendo tudo (é o comando que se roda "antes de confiar")
- Paralelizar a leitura

## Medição

Juriflux, 17.917 arquivos, Windows: `--cached` **4 min 5 s → 49 s** (14.948 arquivos não reabertos); `--staged` com
nada no stage **10,9 s → 1,3 s**. Os ~49 s que sobram são o que mudou desde a última indexação (~2.750 arquivos,
16 s de leitura e regras), `stat` e regras de ignore (~10 s).

## Limite conhecido

O índice só grava os eventos de um arquivo depois de saber se há parser para ele. Um arquivo sem parser com achado
fraco (censurado, não bloqueado) não tem evento guardado, então o modo com cache o trata como limpo; ele não entra
no índice, e a varredura completa o mostra.

## Critérios de aceite

- [x] `tests/integration/test_security_scan_cached.py` verde; `tests/security` verde sem alteração
- [x] `npm run check` verde
