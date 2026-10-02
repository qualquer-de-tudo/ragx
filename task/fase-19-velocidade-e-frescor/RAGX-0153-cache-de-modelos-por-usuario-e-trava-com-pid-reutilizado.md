# RAGX-0153 — Cache de modelos por usuário e trava com PID reutilizado

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-13) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [15-configuracao.md](../../docs/15-configuracao.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [ADR-0004](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `done` |

## Objetivo

A concorrência do índice é sólida (WAL, `busy_timeout=5000`, `index.lock` com pedido pendente: 3 buscadores + 1 indexador em paralelo, 0 erros). Sobram duas arestas (M-13). **1) Modelos por projeto:** o fastembed baixa o modelo para `.ragx/cache/models` de **cada** projeto (**251 MB** neste repo), então cada projeto novo paga o download e o disco de novo. **2) PID reutilizado:** `pid_alive` só pergunta se o número existe; no Windows os PIDs são reciclados rápido, e uma trava de um indexador morto cujo PID foi dado a outro processo vira "viva" para sempre, e nada reindexa até alguém apagar `index.lock`. A tarefa move o cache para uma pasta por usuário e faz a trava conferir **quem** é o dono, não só o número.

## Entregáveis

- [x] **Medir primeiro**: tamanho de `.ragx/cache/models` neste repo e em dois outros projetos com fastembed, e quanto leva o primeiro uso de um projeto novo (download); para a trava, reproduzir a trava "imortal" com um `index.lock` cujo PID é de um processo vivo qualquer (por exemplo o do shell). Registrar em Medição
- [x] `src/ragx/config.py:58-69` (`EmbeddingCfg`): `model_cache_dir: str = "~/.ragx/models"` (a variável `RAGX_EMBEDDING_MODEL_CACHE_DIR` já funciona pelo `_from_env`, linhas 244-262); `docs/15-configuracao.md:217` passa a dizer onde o modelo é guardado
- [x] `src/ragx/embeddings/__init__.py:70-83`: o `cache_dir` do `FastEmbedEmbedder` vem de `models_dir(cfg)`: se `.ragx/cache/models` do projeto **existe e não está vazia**, usa essa (quem já baixou não baixa de novo); senão, `Path(expanduser(cfg.embedding.model_cache_dir))`. Nada é movido, copiado nem apagado automaticamente
- [x] `ragx doctor` (`src/ragx/cli/commands/doctor.py`, perto de `_embedder_status`, linha 150) acrescenta uma linha informativa (nunca muda o veredito): tamanho do cache legado do projeto e como migrar (apagar a pasta; o modelo é baixado uma vez para a pasta do usuário)
- [x] `src/ragx/indexing/lock.py`: `proc_token(pid) -> str | None`, a identidade do processo além do número: Windows, tempo de criação por `GetProcessTimes` (via `ctypes`, com `argtypes` como já é feito para `OpenProcess`, linhas 44-54); Linux, o campo 22 (`starttime`) de `/proc/<pid>/stat`; macOS e demais, `ps -o lstart= -p <pid>`. Qualquer falha devolve `None`
- [x] `try_acquire` (`lock.py:168-181`) grava `"proc": proc_token(os.getpid())` no payload; novo `holder_alive(info) -> bool`: o PID existe (`pid_alive`) **e** (a trava não tem `proc`, ou o token atual do PID é `None`, ou é igual ao gravado). Token diferente ⇒ PID reutilizado ⇒ dono morto, e a trava é assumida por `_take_over`. Trava antiga, sem `proc`, mantém o comportamento de hoje
- [x] Usar `holder_alive` em `try_acquire` (`lock.py:177-179`) e em `src/ragx/indexing/status_file.py:54-56` (o campo `running` do `status.json`, que o painel lê). **Manter** `pid_alive(pid)` com a assinatura atual: os testes o substituem por `monkeypatch` (`tests/integration/test_index_lock_pipeline.py:41`)
- [x] `docs/04-indexacao.md` (trava) e `docs/15-configuracao.md`

## Fora de escopo

- Compartilhar o **mesmo** modelo ONNX carregado entre servidores e processos (a memória de ~680 MB por servidor); a chave do cache de instâncias (`_chave`, com `state_dir`) fica como está
- Copiar ou mover o cache legado, ou apagá-lo sem pedido
- Trocar a trava por `flock`/`msvcrt.locking` ou mexer em `index.pending`
- Cache de modelos do Ollama (é do próprio daemon) e o cache de embedding por chunk (RAGX-0146)

## Critérios de aceite

- [x] Dois projetos novos com fastembed e a mesma configuração usam **a mesma pasta** de modelos; o segundo não baixa nada (teste com `TextEmbedding` falso que registra `cache_dir`)
- [x] Projeto com cache legado não vazio continua usando o dele (sem novo download); projeto sem cache usa `~/.ragx/models`
- [x] Trava cujo PID está vivo mas cujo `proc` não bate é **assumida** em `try_acquire`, e `status.json` não a mostra como `running`
- [x] Trava sem `proc` (versão anterior) e processo realmente vivo continuam bloqueando (compatibilidade)
- [x] Os testes existentes de trava e de status passam sem alteração; `uv run pytest tests/unit/test_index_lock.py tests/integration/test_index_lock_pipeline.py tests/integration/test_status_file.py`

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Cache de modelos por projeto (este repo) | 251 MB (240 MB medidos agora) | 0 MB para projeto novo (pasta do usuário, compartilhada); este repo continua com a cópia dele, nada é apagado sozinho |
| Download no 1º uso de um projeto novo | medir primeiro: 10,1 s (download + carga; a carga sozinha leva 0,9 s) e 240 MB de disco | 0 s e 0 MB a partir do 2º projeto (mesma pasta do usuário); `models_dir` compartilhado, por teste com `TextEmbedding` falso |
| Trava com PID reutilizado | bloqueia até apagar `index.lock` (`try_acquire` = `False`, reproduzido com um `index.lock` cujo PID é de um processo vivo) | assumida (`try_acquire` = `True`); `status.json` não mostra `running` |

Comando: `uv run python -c "from pathlib import Path; print(sum(f.stat().st_size for f in Path('.ragx/cache/models').rglob('*') if f.is_file())//2**20, 'MB')"`.

## Testes

- [x] `tests/unit/test_embeddings.py`: `models_dir(cfg)` com cache legado não vazio, vazio, ausente; `model_cache_dir` por configuração e por `RAGX_EMBEDDING_MODEL_CACHE_DIR`; o `HOME` redirecionado de `tests/conftest.py` é respeitado
- [x] `tests/unit/test_embedder_cache.py`: com `TextEmbedding` falso, dois projetos recebem o mesmo `cache_dir`
- [x] `tests/unit/test_index_lock.py`: `proc_token` do próprio processo é estável entre chamadas; de um filho já encerrado devolve `None`; `holder_alive` com token trocado (`monkeypatch` de `proc_token`) é falso e `try_acquire` assume; trava sem `proc` e PID vivo (`os.getpid()`) continua ocupada
- [x] `tests/integration/test_status_file.py`: `running` nulo quando o token não bate
- [x] `tests/unit/test_index_lock.py`: `proc_token` pelo `GetProcessTimes` real (só Windows, `skipif`); o parse de `/proc/<pid>/stat` com nome contendo espaço e `)` roda em qualquer sistema, porque é uma função pura (`_starttime_do_stat`); a leitura real de `/proc` e o `ps -o lstart=` do macOS não rodaram aqui
- [x] Não lê arquivo do projeto-alvo: sem teste novo em `tests/security`; rodar a suíte inteira

## Notas

- Confirmado em `src/ragx/embeddings/__init__.py:70-83` (`cache_dir=cfg.state_dir / "cache" / "models"`), `src/ragx/indexing/lock.py:57-78,168-181` e `src/ragx/indexing/status_file.py:54-56`. Os dois únicos usuários de `pid_alive` em `src/` são `lock.py` e `status_file.py`.
- Armadilha de compatibilidade: `tests/integration/test_index_lock_pipeline.py:41` troca `lock.pid_alive` por `lambda pid: True`; `holder_alive` precisa chamar `pid_alive` pelo nome do módulo (resolvido na hora da chamada) para o `monkeypatch` continuar valendo.
- Linux: o nome do processo no `/proc/<pid>/stat` fica entre parênteses e pode ter espaços e `)`; o campo 22 só é contado depois do **último** `)`. `starttime` é em ticks desde o boot: serve como identidade (não como hora), que é o que se quer.
- macOS: `ps -o lstart=` custa ~10 ms por chamada; só roda quando há trava contestada e na hora de gravar a própria, aceitável.
- Windows: o PID de um processo encerrado pode ser reaproveitado em segundos; `OpenProcess` falha com `ERROR_ACCESS_DENIED` para processos de outro usuário (hoje isso conta como vivo) e `proc_token` também pode falhar aí: devolver `None` e seguir como "vivo", sem arriscar assumir trava de dono real.
- A pasta do usuário `~/.ragx` já é a do hub (`hub.path = "~/.ragx/hub"`, `config.py:120`); `~/.ragx/models` convive com ela.
- Se a medição mostrar que o cache do modelo já está em `~/.cache` (variável `FASTEMBED_CACHE_PATH` ou do HF) para os usuários reais, registrar e manter só a parte da trava.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0153)` na branch `feat/v2`

## Andamento

- 2026-10-01 — **Medido primeiro** (`scripts/medir_modelo_e_trava.py`, novo): cache deste repo 240 MB; primeiro uso do fastembed numa pasta de modelos vazia 10,1 s (download de 5 arquivos + carga) contra 0,9 s só com a carga; `FASTEMBED_CACHE_PATH` não está definida, então o modelo mesmo ia para `.ragx/cache/models`. A trava imortal reproduzida: `index.lock` com o PID de um processo vivo e `proc` de outra era, `try_acquire` devolvia `False`.
- **Feito**: `EmbeddingCfg.model_cache_dir` (`~/.ragx/models`, vazio = comportamento antigo; `RAGX_EMBEDDING_MODEL_CACHE_DIR` funciona sem código novo); `embeddings.models_dir(cfg)` e `legacy_models_dir(cfg)` (cache legado não vazio continua valendo, nada é movido nem apagado); linha informativa `Cache de modelos` no `ragx doctor` (sempre `ok=True`, nunca levanta); `lock.proc_token` (Windows `GetProcessTimes` com `argtypes`, Linux `starttime` de `/proc/<pid>/stat` por função pura, macOS `ps -o lstart=` via `procs.run_quiet`), `lock.holder_alive`, `proc` gravado em `try_acquire`; `status_file` e `context.engine._indexando` usam `holder_alive`. `pid_alive(pid)` mantido, e `holder_alive` o chama pelo módulo, então o `monkeypatch` de `tests/integration/test_index_lock_pipeline.py` continua valendo.
- **Fora da lista da tarefa, mas necessário**: (1) a tarefa dizia que `lock.py` e `status_file.py` eram os únicos usuários de `pid_alive`; `context/engine.py::_indexando` também era, e com PID reutilizado o cache de contexto acharia que há indexação para sempre; trocado por `holder_alive`. (2) `touchq.claim` apagava a fila inteira quando a leitura do arquivo recém-tomado falhava (qualquer `OSError` virava "fila vazia"): edições na fila se perdiam e o índice ficava velho sem aviso, e foi isso que fez `test_dois_claim_concorrentes...` falhar de vez em quando sob carga (eu havia tratado como mero atraso do teste). Agora relê (5 tentativas) e, se persistir, devolve o arquivo à fila sem sobrescrever uma fila nova; testes reproduzem a perda no código antigo. (3) `ragx doctor` ganhou o teste que a tarefa não pedia.
- **Verificado**: `test_index_lock` (+10), `test_status_file` (+1), `test_embeddings` (+6), `test_embedder_cache` (+2), `test_touchq` (+2); os testes de trava e de status que já existiam passaram sem alteração. Mutação deliberada (`holder_alive` ignorando o token): os testes de PID reutilizado e de `status.json` falham. Suíte `-m "not slow"` 1929 passed, `tests/security` verde, `ruff`, `mypy`. Uma rodada completa deu `test_latencia_do_lembrete_dentro_do_teto` 667 ms contra o teto de 400 ms com a suíte inteira levando 81 s (a máquina estava carregada); isolado passa em 3 de 3 e a rodada seguinte ficou verde.
- **Não verificado**: Linux e macOS (só a função pura de parse do `/proc` roda em qualquer sistema; o `ps -o lstart=` nunca foi executado); processo de outro usuário no Windows (`ERROR_ACCESS_DENIED`) só por teste com `proc_token` simulado como `None`; migração do cache legado deste repo (não mexi: 240 MB seguem em `.ragx/cache/models`, `ragx doctor` explica como).

