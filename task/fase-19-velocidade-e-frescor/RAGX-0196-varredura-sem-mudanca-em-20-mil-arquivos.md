# RAGX-0196 — Varredura sem mudança em 20 mil arquivos (S4)

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0129, RAGX-0130, RAGX-0139 |
| **Documentação** | [26-resultados-v2.md](../../docs/26-resultados-v2.md) (S4) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `review` |

## Objetivo

A meta S4 da spec 25 é indexar sem mudança um repositório de ~20 mil arquivos em **≤ 1,5 s**. O relatório da v2 mediu **7,69 s** num projeto sintético de 20.000 arquivos e deixou a causa sem investigação. Esta tarefa investiga onde vai o tempo e só aplica o que não mexe no Security Gate nem na frescura.

## Entregáveis

- [x] **Medir primeiro e achar o custo**: perfil da rodada sem mudança e microbenchmark isolado da varredura (`scripts/medir_varredura.py`)
- [ ] **NÃO ATENDIDO**: levar a rodada sem mudança de 20 mil arquivos a ≤ 1,5 s. Nenhuma otimização segura foi achada (ver Medição)
- [x] Registrar a decisão sobre cada candidata a otimização, com o motivo de ter sido aplicada ou recusada

## Fora de escopo

- Trocar o `pathspec` por outro motor de ignore ou reescrever o `IgnoreEngine` (é parte do Security Gate)
- Guardar o resultado da varredura entre rodadas (um cache que decide "nada mudou" sem olhar o disco quebra a promessa de frescura)
- Mudar o formato do índice

## Critérios de aceite

- [ ] **NÃO ATENDIDO**: rodada sem mudança em 20 mil arquivos ≤ 1,5 s (continua em torno de 3,7 s no pipeline completo)
- [x] O custo por arquivo está medido e atribuído por função
- [x] Nada que enfraqueça o Gate ou a frescura foi aplicado

### Medição

Projeto sintético de 20.000 arquivos Python (`scripts/medir_indice_inicial.py`, `hashing`, 4 workers), Windows, 02/10/2026:

| Métrica | Valor |
|---|---|
| Rodada sem mudança, relatório da v2 | 7,69 s |
| Rodada sem mudança, esta tarefa (duas rodadas) | 3,70 s e 3,75 s |
| `iter_candidates` isolado (`scripts/medir_varredura.py --arquivos 20000`) | 2,97 a 3,09 s, ~150 µs por arquivo |

A diferença entre 7,69 s e ~3,7 s não veio de código desta tarefa: o número do relatório foi medido em outra condição de máquina. Não afirmo ganho da v2 sobre ele.

Perfil do `iter_candidates` (cProfile, tempo próprio, 20.320 arquivos decididos):

| Custo | Tempo | Observação |
|---|---:|---|
| `nt.stat` | 1,30 s | uma syscall por arquivo |
| `pathspec` (`match_file`, 84 padrões por arquivo, 1,7 milhão de `re.search`) | 1,46 s | o `should_ignore` do Gate |
| pathlib (`relative_to`, `_str_normcase`, `_parse_path`) | ~1,2 s | criação de objetos `Path` |

(Os tempos do perfil incluem o custo do próprio cProfile; a soma passa do total medido sem ele.)

Candidatas:

- **`inner` calculado uma vez** (evita um `relative_to` por arquivo): aplicada e medida, **sem ganho mensurável** (3,09 s contra 2,97–3,06 s, dentro do ruído). Revertida.
- **`DirEntry.stat()` no lugar de `os.stat`**: evitaria a syscall (até ~1,3 s), mas no Windows o tamanho e o mtime vêm da enumeração do diretório e podem estar defasados para um arquivo aberto para escrita. É o oposto do que a v2 promete (nunca raciocinar sobre código velho). **Recusada.**
- **Menos padrões no `IgnoreEngine` / cache por diretório**: mexe no Security Gate (ignore antes do parser). Fora de escopo aqui; exigiria o ADR e os testes de `tests/security`.

Mesmo a soma das duas candidatas arriscadas não chegaria a 1,5 s: o piso do `os.scandir` + `stat` por arquivo já é da ordem de 1 s.

## Andamento

- 2026-10-02 — Perfil feito, `scripts/medir_varredura.py` criado. **S4 continua não atingida**: o custo é por arquivo, em Python puro (stat, pathspec, pathlib), sem atalho seguro. No repositório real (850 documentos) a rodada sem mudança leva 0,21 s. Fica em `review`: uma pessoa decide se S4 vale uma reescrita do caminho quente (por exemplo, varredura em Rust/`os.scandir` com ignore compilado) ou se a meta passa a ser por tamanho de repositório.
- Também entra aqui o fallback do pool de processos (`indexing/parallel.py`): `RuntimeError` (programa sem a guarda `if __name__ == "__main__"`, que o spawn do Windows reexecuta) e `OSError` caem para o índice sequencial, com o mesmo resultado; teste em `tests/integration/test_index_parallel.py`.
