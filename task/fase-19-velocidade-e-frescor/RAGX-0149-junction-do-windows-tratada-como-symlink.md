# RAGX-0149 — Junction do Windows tratada como symlink

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,25d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-13) · [25-spec-v2.md](../../docs/25-spec-v2.md) (princípio 1) · [02-seguranca.md](../../docs/02-seguranca.md) (ameaça A8) · [04-indexacao.md](../../docs/04-indexacao.md) · [ADR-0008](../../docs/adr/ADR-0008-security-gate-antes-do-parser.md) |
| **Status** | `done` |

## Objetivo

A guarda anti-escape do walker só vale para `is_symlink()`. No Windows uma **junction** (`mklink /J`, o que o pnpm cria, e que não exige privilégio) não é symlink para o Python: ela passa na guarda e é percorrida. Reproduzido na auditoria: `linkout/notes.md`, **fora** do projeto, foi indexado (I-13). O conteúdo ainda passa pelo Security Gate, então não é vazamento de segredo, mas é leitura fora da raiz, que a ameaça A8 diz que o walker recusa, e hoje não há teste nenhum da guarda de symlink em `tests/security`.

## Entregáveis

- [x] **Reproduzir primeiro** com um teste que falha: junction para pasta fora da raiz, com `index.follow_symlinks` falso e verdadeiro; registrar o resultado atual em Medição
- [x] `src/ragx/security/links.py` (novo, só stdlib, tipado para o `mypy --strict` do pacote): `is_link(path)` verdadeiro para symlink **ou** junction. Em Python ≥ 3.12 usa `os.path.isjunction`/`DirEntry.is_junction`; em 3.11 (`requires-python = ">=3.11"`, `pyproject.toml:9`), no Windows, `os.lstat(path).st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT`. **Não** tratar qualquer reparse point como link: pastas do OneDrive (arquivos sob demanda) e `AppExecLink` também são reparse points e não são junctions
- [x] `src/ragx/walk.py:161-167` (`_walk`): trocar `entry.is_symlink()` por `is_link(entry)`, só consultar junction quando `is_dir()` (poucas pastas, nenhum syscall extra por arquivo). Com `follow_symlinks=False` (padrão) a junction é pulada; com `True` segue só se `entry.resolve()` ficar dentro da raiz, como o symlink
- [x] `src/ragx/security/ignore_engine.py:102,121` (`_descobrir`): mesma troca, para que `.gitignore` de dentro de uma junction para fora da raiz não seja lido
- [x] `src/ragx/sync/rehydrate.py:143-158` (`_lines`): lê `root / rel`, com `rel` vindo de `knowledge/documents/*.json`, **sem** checar que o caminho fica dentro da raiz. Recusar `rel` absoluto, com `..` ou que resolva (symlink/junction) para fora, tratando como arquivo ausente. É achado lateral: **reproduzir com teste antes de mexer** e, se não reproduzir, registrar em Andamento
- [x] Documentar o comportamento em `docs/02-seguranca.md` (A8 cobre junction) e `docs/04-indexacao.md` (`index.follow_symlinks` e junction), com o aviso de que junctions **dentro** da raiz também deixam de ser indexadas por padrão

## Fora de escopo

- Qualquer outro tipo de reparse point do Windows (cloud files, WSL, dedup)
- Mudar o padrão de `index.follow_symlinks` ou o comportamento de symlink no POSIX
- A poda de diretórios (RAGX-0129) e o arquivo travado (RAGX-0133), que também mexem em `walk.py`: aplicar por cima, sem reescrever
- Percorrer o `node_modules` do pnpm: continua podado pelo `.gitignore`, e a regra do `IgnoreEngine` de visitar cada pasta uma vez (`test_pasta_alcancada_por_varios_links_e_visitada_uma_vez`) não muda

## Critérios de aceite

- [x] Junction para fora da raiz: **nenhum** arquivo de lá entra em `documents` nem em `chunks`, com `follow_symlinks` falso **e** verdadeiro (antes: indexado)
- [x] Symlink para fora da raiz: idem, em Linux e macOS (hoje sem teste)
- [x] Junction para dentro da raiz: não indexada duas vezes (padrão) e seguida uma vez só com `follow_symlinks = true`
- [x] Pasta com reparse point de outro tipo (simulado) continua indexada
- [x] `uv run pytest tests/security` e `uv run mypy src/ragx/core src/ragx/security` verdes

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Arquivos de fora da raiz indexados via junction | 1 (`linkout/notes.md`; reproduzido, com `follow_symlinks` falso e verdadeiro) | **0** |
| Teste de symlink/junction em `tests/security` | 0 | **7** em `test_walker_links.py` (+ 5 em `tests/unit/test_links.py`) |

Comando: `uv run pytest tests/security/test_walker_links.py -q`.

## Testes

- [x] `tests/security/test_walker_links.py` (novo): junction (`_winapi.CreateJunction`, só Windows; como `_link_dir` em `tests/unit/test_ignore_engine.py:59-66`) e symlink (POSIX) para pasta fora da raiz, com `follow_symlinks` falso e verdadeiro: o arquivo de fora não entra e a pasta de dentro continua indexada
- [x] `tests/security/test_walker_links.py`: junction para dentro da raiz (padrão: não indexa duas vezes; `follow_symlinks = true`: uma vez)
- [x] `tests/unit/test_links.py` (novo): `is_link` em diretório comum, symlink e junction; reparse point que não é `MOUNT_POINT` (monkeypatch de `os.lstat` com `st_reparse_tag` de cloud files) devolve falso; caminho inexistente devolve falso sem lançar
- [x] `tests/unit/test_ignore_engine.py`: `.gitignore` dentro de junction para fora da raiz não vira fonte; o teste de visita única continua verde
- [x] `tests/security/test_walker_links.py` ou `tests/integration/test_sync.py`: `knowledge/documents/x.json` com `rel_path` `../fora.txt`, absoluto e via junction → `_lines` devolve `None`, `report.missing` conta, nada fora da raiz é lido

## Notas

- Confirmado em `src/ragx/walk.py:161-167` (`entry.is_symlink()` e depois `target.is_relative_to(root)`; junction cai direto em `entry.is_dir()` e entra na pilha), `src/ragx/security/ignore_engine.py:102,121` e `src/ragx/sync/rehydrate.py:143-158` (nenhuma âncora na raiz). O módulo novo fica em `ragx.security` porque `walk.py` importa o gate; o contrário criaria ciclo.
- Mudança de comportamento: junctions **dentro** do projeto (por exemplo um atalho de desenvolvimento) deixam de ser indexadas pelo padrão, como os symlinks. Quem precisa ativa `index.follow_symlinks`. Dizer no CHANGELOG, em "Alterado".
- `os.lstat` em Windows com `st_reparse_tag` existe desde o Python 3.8; `stat.IO_REPARSE_TAG_MOUNT_POINT` também. Python 3.12 acrescentou `os.path.isjunction`, que **não** existe no 3.11 do `requires-python`.
- `_winapi.CreateJunction` não exige privilégio nem Modo Desenvolvedor; criar symlink no Windows exige, então o teste de symlink é só POSIX.
- A suíte roda com `HOME` redirecionado (`tests/conftest.py`); a pasta "de fora" do teste deve estar em `tmp_path`, irmã da raiz do projeto, para não depender da máquina.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui, com junction de verdade via `_winapi.CreateJunction`; Linux e macOS pelo CI, com symlink)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0149)` na branch `feat/v2`

## Andamento

2026-09-30. Reproduzido primeiro: 5 testes vermelhos (junction para fora indexada nos dois modos de `follow_symlinks`;
junction interna indexada por padrão; `.gitignore` dentro de junction para fora lido; `_lines(raiz, "../fora.txt")` devolveu
`['segredo-de-fora']`, ou seja, o achado lateral de `sync/rehydrate` SE CONFIRMOU). Implementado: `ragx/security/links.py`
(`is_link`, `is_junction`; só `IO_REPARSE_TAG_MOUNT_POINT`, via `os.lstat().st_reparse_tag`, igual no 3.11 e no 3.12+; o ambiente
roda Python 3.13); `walk._walk` usa `entry.is_symlink() or (entry.is_dir() and is_junction(entry))` (nenhum syscall a mais por
arquivo; fora do Windows `is_junction` devolve falso sem syscall); `IgnoreEngine._descobrir` pula junction; `rehydrate._dentro_da_raiz`
recusa `rel` absoluto, com `..` ou que resolva para fora. Docs: `02-seguranca.md` (A8) e `04-indexacao.md` (a frase antiga dizia que
symlink interno era seguido por padrão; na verdade só com `follow_symlinks = true`, corrigido). CHANGELOG: o aviso de mudança de
comportamento (junction interna deixa de ser indexada por padrão) está registrado. Fast suite, `tests/security`, `ruff`, `mypy` verdes.
Correção colateral: as entradas de CHANGELOG da 0133 e desta tinham caído na seção da beta.4; movidas para `[Não lançado]`.
