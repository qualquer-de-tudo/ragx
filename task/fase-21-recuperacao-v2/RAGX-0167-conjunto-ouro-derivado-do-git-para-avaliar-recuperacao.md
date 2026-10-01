# RAGX-0167 — Conjunto-ouro derivado do git para avaliar recuperação

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0099` (fase 14) |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #11) · [05-busca.md](../../docs/05-busca.md) · [14-cli.md](../../docs/14-cli.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

`tests/eval/queries.yaml` tem 26 consultas escritas à mão: com n=26 o IC95% de recall@5 tem largura ~0,33 e nenhuma mudança de recuperação é falsificável (por isso existe a `RAGX-0099`, que amplia a mão-de-obra para 150). O próprio git já traz um gabarito grátis e que cresce sozinho: a **mensagem do commit é a consulta** e os **arquivos alterados são os documentos relevantes** (ContextBench, arxiv 2602.05892). Este repo tem **172 commits sem merge**, mediana de 4 arquivos por commit, 103 deles com 1 a 5 arquivos (medido com `git log --no-merges --name-only`); falta saber quantos sobram depois dos filtros, e esse é o primeiro entregável.

## Entregáveis

- [ ] **Medir primeiro**: script descartável (ou `--dry-run` do comando abaixo) que conta, nos 172 commits, quantos restam após cada filtro (tipo `chore(release)`, arquivos > 8, sem arquivo indexado, só `CHANGELOG.md`/`knowledge/`/lockfile); registrar o funil em Andamento
- [ ] `gitinfo.py`: `log_commits(root, limit, since=None)` devolve `(hash, subject, files)` por `git log --no-merges --name-status -M -z`; `git()` (linha 24) ganha `timeout` opcional, porque os 5 s fixos de `_TIMEOUT_S` não cobrem um log longo. Só hash, assunto e caminhos: autor e e-mail **nunca** saem do git
- [ ] `src/ragx/search/gold.py`: `derive_cases(cfg, commits)` — consulta = assunto sem o prefixo `tipo(escopo):` e sem o sufixo `(RAGX-0xxx)`; gabarito = arquivos do commit que **existem hoje em `documents`** (some o que foi apagado ou renomeado depois), excluindo `CHANGELOG.md`, `knowledge/`, lockfiles e arquivos gerados; descarta commit com mais de `max_files` (padrão 8) e consulta com menos de 3 palavras
- [ ] Cada caso registra `commit` (hash curto), `kind` (`code`, `doc` ou `mixed`, pelo `documents.doc_kind`) e `note` (`derivado de <hash>`), para permitir recorte; `load_cases` (`search/evaluation.py:73`) já ignora chaves extras, e `EvalCase` ganha `commit`/`kind` opcionais
- [ ] Comando `ragx gold build [--limit N] [--max-files 8] [--out tests/eval/gold-git.yaml] [--dry-run]` em `cli/commands/gold_cmd.py`, registrado em `cli/main.py` com `app.add_typer(...)`; o avaliador é o que já existe: `ragx eval --queries tests/eval/gold-git.yaml`
- [ ] Saída **determinística** (ordem por data do commit e hash; sem timestamp no cabeçalho além do hash do HEAD de origem) para o arquivo ficar estável no git
- [ ] Gerar e versionar `tests/eval/gold-git.yaml` a partir do HEAD de `feat/v2`; documentar o comando em `docs/14-cli.md` (há teste que cobra todo comando documentado) e a seção de avaliação em `docs/05-busca.md`

## Fora de escopo

- Substituir ou editar `tests/eval/queries.yaml` (continua o conjunto manual, ampliado pela `RAGX-0099`)
- Avaliar geração, ou usar LLM para reescrever a consulta
- A/B com e sem o MCP via `claude -p` (`RAGX-0162`, fase 20)
- Avaliação em outro repositório (a ferramenta aceita qualquer raiz, mas só este repo é gerado e versionado aqui)

## Critérios de aceite

- [ ] `uv run ragx gold build --dry-run` imprime o funil e termina em menos de **10 s** no repo (172 commits)
- [ ] O arquivo gerado tem **≥ 100** consultas; com ≥ 100, a largura do IC95% de recall@5 (`MAX_CI_WIDTH = 0.20`, `evaluation.py:31`) deve ficar `conclusive`. Se o funil der menos, registrar o número real e a largura em Notas, sem baixar os filtros para enfeitar
- [ ] `ragx gold build` duas vezes seguidas gera arquivos **byte-idênticos**
- [ ] `uv run ragx eval --queries tests/eval/gold-git.yaml --mode all` roda em menos de **2 min** e imprime os três modos; o resultado entra em Medição
- [ ] Nenhum autor, e-mail ou corpo de commit aparece no YAML; consulta que dispare o `SecurityScanner` é descartada e contada, sem ser escrita

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Consultas de avaliação com IC conclusivo | 26 manuais, largura ~0,33 | (medir) |
| recall@5 keyword / semantic / hybrid no ouro do git | n/a | (medir) |
| Tempo de `ragx eval --queries tests/eval/gold-git.yaml` | n/a | (medir) |

Comando: `uv run ragx gold build --dry-run && uv run ragx eval --queries tests/eval/gold-git.yaml --json`

## Testes

- [ ] `tests/unit/test_gold.py`: prefixo e sufixo do assunto saem; arquivo inexistente no índice sai do gabarito; commit grande e consulta curta são descartados; ordem estável
- [ ] `tests/integration/test_gold.py`: repo git temporário com 3 commits e índice `hashing`; `derive_cases` devolve o esperado e o `evaluate` roda sobre ele (usar o helper `_repo` de `tests/unit/test_gitinfo.py` como modelo)
- [ ] `tests/security/test_gold_secrets.py`: commit cujo assunto contém um segredo falso (de `tests/fixtures/secrets_under_test.py`) não chega ao YAML, e o relatório conta 1 descarte
- [ ] `tests/unit/test_documentacao.py` continua verde (comando novo documentado)

## Notas

Vazamento é inevitável e aceito: o índice está no HEAD, que já contém a mudança do commit; o conjunto mede "dada a intenção, ache o lugar", não previsão. Por isso `kind` e `commit` ficam no arquivo, para recortar. Commits de mensagem genérica ("fix", "wip") caem no filtro de 3 palavras; mensagem em português com identificadores em inglês é o caso comum deste repo e serve bem à busca híbrida. `ragx.search` já está autorizado a ler artefatos próprios (`tests/security/test_architecture.py`); o git entra por `ragx.procs.run_quiet` via `gitinfo`, nunca por `subprocess` direto.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0167)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
