# RAGX-0167 — Conjunto-ouro derivado do git para avaliar recuperação

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0099` (fase 14) |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #11) · [05-busca.md](../../docs/05-busca.md) · [14-cli.md](../../docs/14-cli.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `done` |

## Objetivo

`tests/eval/queries.yaml` tem 26 consultas escritas à mão: com n=26 o IC95% de recall@5 tem largura ~0,33 e nenhuma mudança de recuperação é falsificável (por isso existe a `RAGX-0099`, que amplia a mão-de-obra para 150). O próprio git já traz um gabarito grátis e que cresce sozinho: a **mensagem do commit é a consulta** e os **arquivos alterados são os documentos relevantes** (ContextBench, arxiv 2602.05892). Este repo tem **172 commits sem merge**, mediana de 4 arquivos por commit, 103 deles com 1 a 5 arquivos (medido com `git log --no-merges --name-only`); falta saber quantos sobram depois dos filtros, e esse é o primeiro entregável.

## Entregáveis

- [x] **Medir primeiro**: script descartável (ou `--dry-run` do comando abaixo) que conta, nos 172 commits, quantos restam após cada filtro (tipo `chore(release)`, arquivos > 8, sem arquivo indexado, só `CHANGELOG.md`/`knowledge/`/lockfile); registrar o funil em Andamento
- [x] `gitinfo.py`: `log_commits(root, limit, since=None)` devolve `(hash, subject, files)` por `git log --no-merges --name-status -M -z`; `git()` (linha 24) ganha `timeout` opcional, porque os 5 s fixos de `_TIMEOUT_S` não cobrem um log longo. Só hash, assunto e caminhos: autor e e-mail **nunca** saem do git
- [x] `src/ragx/search/gold.py`: `derive_cases(cfg, commits)` — consulta = assunto sem o prefixo `tipo(escopo):` e sem o sufixo `(RAGX-0xxx)`; gabarito = arquivos do commit que **existem hoje em `documents`** (some o que foi apagado ou renomeado depois), excluindo `CHANGELOG.md`, `knowledge/`, lockfiles e arquivos gerados; descarta commit com mais de `max_files` (padrão 8) e consulta com menos de 3 palavras
- [x] Cada caso registra `commit` (hash curto), `kind` (`code`, `doc` ou `mixed`, pelo `documents.doc_kind`) e `note` (`derivado de <hash>`), para permitir recorte; `load_cases` (`search/evaluation.py:73`) já ignora chaves extras, e `EvalCase` ganha `commit`/`kind` opcionais
- [x] Comando `ragx gold build [--limit N] [--max-files 8] [--out tests/eval/gold-git.yaml] [--dry-run]` em `cli/commands/gold_cmd.py`, registrado em `cli/main.py` com `app.add_typer(...)`; o avaliador é o que já existe: `ragx eval --queries tests/eval/gold-git.yaml`
- [x] Saída **determinística** (ordem por data do commit e hash; sem timestamp no cabeçalho além do hash do HEAD de origem) para o arquivo ficar estável no git
- [x] Gerar e versionar `tests/eval/gold-git.yaml` a partir do HEAD de `feat/v2`; documentar o comando em `docs/14-cli.md` (há teste que cobra todo comando documentado) e a seção de avaliação em `docs/05-busca.md`

## Fora de escopo

- Substituir ou editar `tests/eval/queries.yaml` (continua o conjunto manual, ampliado pela `RAGX-0099`)
- Avaliar geração, ou usar LLM para reescrever a consulta
- A/B com e sem o MCP via `claude -p` (`RAGX-0162`, fase 20)
- Avaliação em outro repositório (a ferramenta aceita qualquer raiz, mas só este repo é gerado e versionado aqui)

## Critérios de aceite

- [x] `uv run ragx gold build --dry-run` imprime o funil e termina em menos de **10 s** no repo (172 commits)
- [x] O arquivo gerado tem **≥ 100** consultas; com ≥ 100, a largura do IC95% de recall@5 (`MAX_CI_WIDTH = 0.20`, `evaluation.py:31`) deve ficar `conclusive`. Se o funil der menos, registrar o número real e a largura em Notas, sem baixar os filtros para enfeitar
- [x] `ragx gold build` duas vezes seguidas gera arquivos **byte-idênticos**
- [x] `uv run ragx eval --queries tests/eval/gold-git.yaml --mode all` roda em menos de **2 min** e imprime os três modos; o resultado entra em Medição
- [x] Nenhum autor, e-mail ou corpo de commit aparece no YAML; consulta que dispare o `SecurityScanner` é descartada e contada, sem ser escrita

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Consultas de avaliação com IC conclusivo | 26 manuais, largura ~0,33 | **134** derivadas do git, largura **0,15 / 0,17 / 0,16** (keyword / semantic / hybrid): conclusivo |
| recall@5 keyword / semantic / hybrid no ouro do git | n/a | **0,72 / 0,49 / 0,60** (MRR 0,51 / 0,34 / 0,47; nDCG@10 0,42 / 0,23 / 0,33) |
| Tempo de `ragx eval --queries tests/eval/gold-git.yaml` | n/a | **~10 s** (134 consultas, três modos); `ragx gold build --dry-run`: 1,1 s |

Comando: `uv run ragx gold build --dry-run && uv run ragx eval --queries tests/eval/gold-git.yaml --json`

## Testes

- [x] `tests/unit/test_gold.py`: prefixo e sufixo do assunto saem; arquivo inexistente no índice sai do gabarito; commit grande e consulta curta são descartados; ordem estável
- [x] `tests/integration/test_gold.py`: repo git temporário com 3 commits e índice `hashing`; `derive_cases` devolve o esperado e o `evaluate` roda sobre ele (usar o helper `_repo` de `tests/unit/test_gitinfo.py` como modelo)
- [x] `tests/security/test_gold_secrets.py`: commit cujo assunto contém um segredo falso (de `tests/fixtures/secrets_under_test.py`) não chega ao YAML, e o relatório conta 1 descarte
- [x] `tests/unit/test_documentacao.py` continua verde (comando novo documentado)

## Notas

Vazamento é inevitável e aceito: o índice está no HEAD, que já contém a mudança do commit; o conjunto mede "dada a intenção, ache o lugar", não previsão. Por isso `kind` e `commit` ficam no arquivo, para recortar. Commits de mensagem genérica ("fix", "wip") caem no filtro de 3 palavras; mensagem em português com identificadores em inglês é o caso comum deste repo e serve bem à busca híbrida. `ragx.search` já está autorizado a ler artefatos próprios (`tests/security/test_architecture.py`); o git entra por `ragx.procs.run_quiet` via `gitinfo`, nunca por `subprocess` direto.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0167)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **`blocked`, nada implementado.** depende da RAGX-0099 (fase 14, ampliar o conjunto de avaliação), que continua `todo` e é da fase que o loop não pega sozinho. Verificado nos arquivos das dependências (todas ainda com `Status = todo`/`review`). Quando a dependência fechar, voltar o status para `todo` e retomar daqui.

## Andamento

- 2026-10-02 — **Desbloqueada** (a 0099 fechou). **Funil medido primeiro** (`ragx gold build --dry-run`, 1,1 s): 251 commits sem merge (a task dizia 172, o histórico cresceu), 7 de release, 0 com segredo, 1 de consulta curta, 19 sem arquivo indexado hoje, 90 com arquivos demais (> 8), **134 casos** (≥ 100: o critério vale sem baixar filtro nenhum).
- **Feito**: `gitinfo.log_commits` e `Commit` (só hash, assunto, caminhos e `%ct` só para ordenar), `git()` com `timeout` opcional (o log usa 60 s); `search/gold.py` (`clean_subject`, `derive_cases`, `render_yaml`, `Funil`); `EvalCase` ganhou `commit` e `kind`; `ragx gold build [--limit] [--max-files] [--out] [--dry-run]`; `tests/eval/gold-git.yaml` gerado e versionado a partir do HEAD `442b2ba`; docs em `docs/14-cli.md` e `docs/05-busca.md`.
- **Medido**: keyword 0,72 [0,64–0,79], semantic 0,49 [0,40–0,57], hybrid 0,60 [0,51–0,68]; todos conclusivos. **Dois conjuntos independentes (152 manuais, 134 do git) dão o mesmo ordenamento, keyword > hybrid > semantic**: é o ponto de partida honesto para a RAGX-0105 (recalibrar o RRF).
- **Achado de segurança que o teste pegou**: o `SecurityScanner` NÃO reconhece vários dos segredos falsos da fixture quando aparecem soltos numa frase de assunto de commit (`Tr0ub4dor&3xKcd9Zq`, `pG7x2Qm9ZvLk4Rt8`, os de 32 e 40 caracteres, as chaves PEM): as regras dependem de contexto (`chave = valor`) ou de formato conhecido. Meu primeiro teste falhou em 8 dos 10. Corrigi no `gold.py` com `_tem_segredo`: além do scanner, descarta o assunto que tenha uma palavra de 16+ caracteres com letra e dígito e entropia ≥ 3 (conservador: um hash de commit no assunto também cai fora). Os 10 segredos agora são descartados e contados. **O scanner em si não foi mudado**: é uma limitação do reconhecimento de segredo sem contexto, que vale para qualquer superfície que passe texto solto por ele; registro aqui para uma pessoa decidir se vira tarefa.
- Testes: `tests/unit/test_gold.py` (6), `tests/integration/test_gold_git.py` (4: log só com hash/assunto/caminhos, derive+evaluate num repositório temporário, comando determinístico e sem autor nem corpo), `tests/security/test_gold_secrets.py` (10, um por segredo da fixture). O de integração tem outro nome porque dois `test_gold.py` colidem no pytest (sem `__init__`).
- **Mudança de configuração**: `ragx.toml` passou a excluir `tests/eval/` inteiro (antes só `queries.yaml`) do índice do repositório.
- **Não verificado**: Linux e macOS (o git em `core.quotepath=off` e caminhos com acento só no Windows); histórico muito longo (o timeout de 60 s do log).
