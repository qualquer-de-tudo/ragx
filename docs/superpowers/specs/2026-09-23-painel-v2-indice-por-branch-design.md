# Painel v2 e índice que acompanha a branch

**Status:** aprovado em brainstorm em 2026-09-23. Duas partes, dois planos:
Parte A (núcleo do RAGX) e Parte B (painel desktop). A Parte B depende da A.

## O problema

Três coisas apareceram ao usar o painel v1 com os 9 projetos da máquina:

1. **8 de 9 projetos estavam sem nenhum embedding.** Todos usam o provedor
   padrão (`ollama` com `nomic-embed-text`) e foram indexados em 2026-09-21
   antes do container do Ollama existir. Pelo ADR-0004, falha do embedder não
   derruba a indexação: os chunks são gravados e os vetores ficam para um
   `ragx index --embed-only` posterior. Nada rodou esse passo depois, e nada
   avisou. A busca semântica e a híbrida desses projetos caíam para só
   palavra-chave em silêncio.
2. **O índice não sabe de qual branch veio.** Três projetos estão em branches
   de feature (`melhorias-ia-mcp`, `HNS-1487-unificacao-chiesi`,
   `ajuste-ui-mac`), indexados sabe-se lá em qual branch. A
   `docs/12-git-sync.md` promete `ragx init --git-hooks` com um hook
   `post-checkout` que atualiza o índice na troca de branch, mas o comando
   nunca foi implementado (só existe a flag `git_hooks` na config). Nenhum
   projeto tem hook instalado.
3. **O painel só observa.** Adicionar projeto, indexar, gerar embeddings,
   instalar hooks e checar se o Claude Code e o Ollama estão de pé exige
   terminal.

Há ainda um risco de concorrência: a única trava de escrita existente é um
`threading.Lock` dentro do servidor MCP. Hooks em segundo plano, painel, CLI e
o `refresh` do MCP podem escrever no mesmo `knowledge.db` ao mesmo tempo.

## Decisões tomadas no brainstorm

| Pergunta | Decisão |
|---|---|
| Como o índice reage à troca de branch | Um índice por projeto que segue a branch atual. Só os arquivos que divergem são reindexados; chunk id é hash de caminho e conteúdo, então o resto dos embeddings é reaproveitado. |
| O que dispara atualização | Hooks do git (checkout de branch, commit, merge) e o `refresh` que o agente já chama pelo MCP antes de cada tarefa (cobre edições não commitadas). Nenhum processo permanente. |
| Controles no painel | Adicionar e remover projetos, manutenção do índice, hooks por projeto, knowledge versionado. |
| Onboarding | Assistente na primeira abertura, depois acessível pelo menu. |
| Visual | Base do app Perssua: escuro, cards com borda sutil, menu lateral com ícones, selos de estado. |

O desenho dos hooks segue o do graphify (`C:\projects\open-source\graphify`,
`graphify/hooks.py`), que já resolveu o mesmo problema em produção: blocos
marcados que convivem com hooks existentes, caminho do executável gravado na
instalação, execução destacada com log, opt-out por variável de ambiente.

## Não-objetivos

- Um índice guardado por branch ou camadas main + branch. Descartados no
  brainstorm em favor de seguir a branch atual.
- `ragx watch` como serviço permanente.
- Hook `pre-commit` com `ragx security scan --staged`. A doc promete, mas ele
  bloqueia commits e não foi pedido. A doc passa a dizer que não existe ainda.
- Tema claro no painel. O v2 é só escuro, como a referência.
- Remoção dos travessões do repositório (Parte C, spec separada).

---

## Parte A: índice que acompanha a branch

### A1. Proveniência de cada indexação

Nova migração adiciona a `index_runs` as colunas `git_branch`, `git_commit`,
`git_dirty` (0/1) e `source` (texto). `source` identifica quem disparou:
`cli`, `mcp:refresh`, `panel`, `hook:post-checkout`, `hook:post-commit`,
`hook:post-merge`, `watch`, `sync`. Toda passada que escreve no índice grava uma
linha em `index_runs` com esses campos. Fora de um repositório git os campos
de git ficam nulos.

Todos os pontos de escrita passam a aceitar um parâmetro `source` e o repassam:
`index_project`, `sync`, a passada do watcher usada pelo `refresh` e o
`ragx watch`.

### A2. `.ragx/status.json`

Ao final de toda operação de escrita, e no início (para marcar `running`), o
RAGX reescreve `.ragx/status.json` de forma atômica (arquivo temporário e
`os.replace`). `.ragx/` já é ignorado pelo git; o arquivo é local.

```json
{
  "schema_version": 1,
  "written_at": "2026-09-23T12:00:05Z",
  "project": {"id": "2a0786031710", "name": "ragx"},
  "index": {
    "finished_at": "2026-09-23T12:00:05Z",
    "mode": "incremental",
    "source": "hook:post-checkout",
    "branch": "main",
    "commit": "79a81d5b80f9d8777b83d582fd90a71271951249",
    "dirty": false
  },
  "counts": {"documents": 387, "chunks": 3633, "embeddings": 3633, "pending_embeddings": 0},
  "embedding": {"provider": "fastembed", "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"},
  "hooks": {"installed": ["post-checkout", "post-commit", "post-merge"]},
  "running": null,
  "pending": false,
  "last_error": null
}
```

- `running`, quando há operação em curso:
  `{"op": "index", "source": "panel", "pid": 1234, "started_at": "..."}`.
  Quem lê trata um `pid` que não existe mais como `running: null`.
- `last_error`: `{"at": "...", "op": "embed", "message": "..."}`. Falha do
  embedder entra aqui, que é o sinal que faltou no problema 1. Uma passada
  seguinte bem-sucedida limpa o campo.
- A escrita do arquivo vive fora de `ragx.mcp` (ADR-0006), no mesmo padrão de
  `ragx.diagnostics`.

### A3. Defasagem em `ragx status --json`

O comando já existe (`index_cmd.status`) e hoje devolve contagens e o último
run. Passa a incluir:

```json
{
  "freshness": {
    "state": "stale",
    "current": {"branch": "feature-x", "commit": "..."},
    "reasons": [
      {"kind": "branch_changed", "indexed": "main", "current": "feature-x"},
      {"kind": "commits_since_index", "count": 7},
      {"kind": "uncommitted_changes", "files": 12},
      {"kind": "pending_embeddings", "count": 4200}
    ]
  },
  "recent_runs": [
    {"finished_at": "...", "mode": "incremental", "source": "hook:post-commit",
     "branch": "main", "commit": "...", "indexed": 3, "embedded": 11}
  ]
}
```

- `state` é `fresh` quando não há nenhum motivo, `stale` quando há, e
  `unknown` fora de um repositório git ou sem nenhum run registrado.
- `branch_changed`: branch atual diferente da do último run.
- `commits_since_index`: `git rev-list --count <commit_do_indice>..HEAD`,
  só quando o commit do índice é ancestral do HEAD. Se não for (rebase, outra
  branch), o motivo não aparece e `branch_changed` ou o próximo cobre.
- `uncommitted_changes`: arquivos listados por `git status --porcelain`
  (respeitando o ignore do RAGX) cujo mtime é posterior ao `finished_at` do
  último run. Arquivos alterados mas já indexados pelo `refresh` não contam.
- `pending_embeddings`: chunks sem vetor.
- `recent_runs`: os 10 últimos de `index_runs`, para a linha do tempo do
  painel.

### A4. `ragx hooks install | uninstall | status`

- **Onde:** diretório de hooks resolvido por `git rev-parse --git-path hooks`,
  que respeita `core.hooksPath` (husky e afins).
- **Quais:** `post-checkout`, `post-commit`, `post-merge`.
- **Bloco marcado:** o RAGX escreve entre `# ragx-hook-start` e
  `# ragx-hook-end`, anexado ao hook existente. Se o arquivo não existe, cria
  com shebang `#!/bin/sh`. Reinstalar substitui só o bloco. `uninstall` remove
  só o bloco e apaga o arquivo se sobrar apenas o shebang.
- **Conteúdo do bloco:** `[ "${RAGX_SKIP_HOOK:-0}" = "1" ] && exit 0`, depois
  a chamada ao executável do RAGX com caminho absoluto gravado na instalação:
  `"<caminho>/ragx" hook-run <evento> "$@"`. O caminho gravado resolve o caso
  de clientes git gráficos em que o PATH não tem o `ragx`.
- **`ragx hook-run <evento> [args]`** (comando interno, oculto no `--help`):
  - `post-checkout` só age quando o terceiro argumento é `1` (troca de
    branch); `git checkout -- arquivo` não dispara nada;
  - dispara `ragx index --source hook:<evento>` em processo destacado e
    retorna na hora, sem travar o git;
  - no Windows usa `subprocess.Popen` com `DETACHED_PROCESS |
    CREATE_NEW_PROCESS_GROUP`, tentando também `CREATE_BREAKAWAY_FROM_JOB` e
    caindo para sem ele se o job não permitir; em POSIX,
    `start_new_session=True`. É a mesma solução do graphify (#1161), porque o
    shell do Git for Windows não tem `nohup`;
  - a saída vai para `.ragx/logs/hooks.log`.
- **Os hooks rodam só `ragx index` incremental**, com embeddings dos arquivos
  alterados. Não rodam `ragx sync`: o sync regrava `knowledge/`, que é
  versionado, e deixaria a árvore suja a cada commit. Atualizar `knowledge/`
  continua explícito.
- **`ragx hooks status --json`:** eventos instalados, caminho gravado em cada
  um e se ele ainda existe (caminho velho após reinstalar o RAGX aparece como
  `stale`, e o painel oferece reinstalar).
- `ragx init` ganha `--hooks` para instalar junto. O padrão continua sem
  hooks: `init` não mexe em `.git` sem pedido.

### A5. Trava entre processos

- Toda operação que escreve em `knowledge.db` (index em todos os modos, sync,
  passada do watcher/refresh, `graph rebuild`, `dictionary generate`) adquire
  `.ragx/index.lock`, criado com abertura exclusiva e contendo pid, operação,
  origem e início.
- Lock existente com pid vivo: a operação não roda em paralelo. Ela marca
  `pending: true` em `status.json` e:
  - origem hook, painel ou mcp: sai com sucesso na hora;
  - origem CLI interativa: espera até 30 s pela liberação e, se não liberar,
    sai com erro dizendo quem está com a trava.
- Quem está com a trava, ao terminar, confere `pending`. Se estiver marcado,
  limpa a marca e faz mais uma passada incremental (até 3 seguidas), para não
  perder o que chegou durante a execução.
- Lock com pid morto é tomado por quem chegar.
- O `threading.Lock` do servidor MCP continua existindo para serializar as
  chamadas dentro do mesmo processo.

### A6. Progresso legível por máquina

`ragx index --progress` escreve uma linha JSON por evento em stdout:
`{"phase": "scan|chunk|embed", "done": 120, "total": 4200}`, com no máximo
uma linha por segundo por fase, e uma linha final `{"phase": "done", ...}` com
o relatório. É o que o painel usa para barra de progresso e previsão.

### A7. Documentação

- `docs/12-git-sync.md`: seção de hooks reescrita para `ragx hooks`, dizendo
  o que dispara o quê, e que o `pre-commit` não existe ainda.
- `docs/14-cli.md`: `ragx hooks`, `ragx index --source/--progress`, campos
  novos do `ragx status --json`.
- `CHANGELOG.md` na mesma entrega (`[Não lançado]`).

### Testes da Parte A

- Proveniência: run grava branch, commit, dirty e source; fora de git, nulos.
- Defasagem em repositório git de teste: troca de branch, commits novos,
  arquivo modificado depois do run, arquivo modificado antes do run (não
  conta), embeddings pendentes, sem runs (`unknown`).
- Hooks: instalar em diretório sem hook, com hook existente (conteúdo alheio
  preservado), com `core.hooksPath`; reinstalar não duplica; desinstalar
  preserva o alheio; `post-checkout` com flag 0 não dispara; `RAGX_SKIP_HOOK=1`
  não dispara; o disparo é destacado (o hook retorna antes do index terminar).
- Trava: segunda operação com lock vivo marca pending e sai; quem segura a
  trava faz a passada extra; lock de pid morto é tomado.
- `status.json`: escrito atomicamente, `running` durante a operação,
  `last_error` quando o embedder falha e limpo depois.
- Progresso: linhas JSON válidas e fase final presente.
- Os testes arquiteturais existentes continuam passando.

---

## Parte B: painel v2

### B1. Estrutura e visual

- Só tema escuro, com a base do Perssua: fundo preto, cards com borda de 1px
  sutil e cantos de 12px, azul para seleção e ações, verde para "conectado" e
  "atualizado", âmbar para "defasado" e embeddings faltando, vermelho para
  erro. Selos no formato "● Atualizado", "● Defasado", "● Indexando…", sempre
  com texto (cor nunca sozinha).
- Barra superior: busca de projetos ao centro; à direita, o indicador da fila
  ("2 tarefas", abre a lista com progresso) e um ponto de saúde das conexões
  que leva à tela Conexões.
- Menu lateral com ícones: Projetos, Conexões, Como funciona.
- Título da janela: "RAGX Painel".

### B2. Tela Projetos

- Grade de cards. Cada card: nome, pasta relativa à pasta comum, selo de
  estado, branch atual (com aviso quando o índice é de outra branch),
  "Indexado há 2 h", barra de embeddings (âmbar quando faltam) e um botão
  principal que muda com o estado:

  | Estado | Botão |
  |---|---|
  | Embeddings faltando | Gerar embeddings |
  | Defasado | Atualizar agora |
  | Sem hooks | Instalar hooks |
  | Tudo certo | Abrir |

- Filtro segmentado: Todos | Defasados | Com problema.
- Card "+ Adicionar projeto": escolhe uma pasta; o painel roda `ragx init`,
  indexação e registro no hub, com opção (marcada) de instalar hooks.
- Detalhe do projeto (seta de voltar no topo):
  - indicadores do índice (documentos, chunks, embeddings e cobertura);
  - linha do tempo de atualização a partir de `recent_runs`: quando, origem,
    branch e commit, o que mudou; e os motivos de defasagem do momento;
  - hooks: estado e liga/desliga;
  - manutenção: atualizar agora, gerar embeddings faltantes, reindexar do
    zero (pede confirmação);
  - knowledge versionado: `ragx sync`, reconstruir grafo, gerar dicionário,
    com aviso de que alteram arquivos versionados;
  - uso pelos agentes, economia estimada e segurança (o que o v1 já tem);
  - remover do hub (pede confirmação, não apaga nada no disco).

### B3. Tela Conexões

Cards no estilo "Provedores de IA" do Perssua, cada um com selo e ação de
correção. As checagens rodam no processo principal, a cada 30 s e ao abrir a
tela. Nenhuma checagem lança erro: cada uma devolve estado e motivo.

| Card | Conectado quando | Ações |
|---|---|---|
| RAGX CLI | `ragx --version` responde. O caminho é resolvido por `where`/`which` e pelos locais de instalação conhecidos (`%USERPROFILE%\.local\bin`), porque o app aberto pelo menu Iniciar pode ter outro PATH. | Instruções de instalação |
| Claude Code | `mcpServers.ragx` existe em `~/.claude.json` (o arquivo que o instalador e o `ragx mcp install` escrevem) e o comando registrado existe no disco. Mostra também a última chamada MCP registrada em qualquer projeto. | Registrar no Claude Code (`ragx mcp install --client claude-code`) |
| Ollama (Docker) | Container `ollama` rodando (`docker ps`), `GET localhost:11434/api/tags` responde e os modelos usados pelos projetos com provedor `ollama` estão baixados. Mostra quais projetos dependem dele e a velocidade medida de embeddings. | Iniciar container (`docker start ollama`), Baixar modelo (`docker exec ollama ollama pull <modelo>`) |

### B4. Onboarding

Abre na primeira execução ou com o hub vazio. Quatro passos:

1. **Como funciona:** o RAGX indexa localmente em chunks e embeddings; o
   Claude Code consulta o índice pelo MCP em vez de ler arquivos inteiros;
   segredos são bloqueados antes de entrar; os hooks mantêm o índice na
   branch em que você está.
2. **Conexões:** as checagens da B3 com os botões de correção.
3. **Projetos:** o usuário escolhe uma pasta raiz; o painel procura
   `ragx.toml` até 4 níveis abaixo (pulando `node_modules`, `.git`, `.venv`,
   `dist`) e lista os projetos encontrados para marcar. Também dá para
   adicionar pastas novas.
4. **Indexar:** "instalar hooks" vem marcado; as tarefas entram na fila.

Depois, a página "Como funciona" mostra o passo 1 e o botão "Refazer
configuração".

### B5. Arquitetura

- **Fila única de tarefas** no processo principal, uma por vez, porque o
  Ollama é compartilhado. Tipos fechados: adicionar projeto, atualizar,
  gerar embeddings, reindexar do zero, sync, grafo, dicionário, instalar e
  remover hooks, remover do hub, registrar MCP no Claude Code, iniciar
  container, baixar modelo. Cada tarefa roda `ragx`, `docker` ou `claude`
  como processo filho, guarda o log, lê o progresso da A6 quando existe,
  calcula previsão a partir da velocidade medida e pode ser cancelada.
  Fechar o painel com tarefa rodando pede confirmação.
- **Segurança do IPC:** o renderer pede ações por tipo e id de projeto, nunca
  com argumentos livres. O processo principal resolve o caminho a partir do
  hub e recusa ids desconhecidos. Isso fecha a pendência de validação de
  caminho da revisão final do v1.
- **Dados:** o painel lê `.ragx/status.json` de cada projeto. Sem o arquivo
  (projeto ainda não tocado por um RAGX novo), cai para o leitor SQLite
  atual (`sql.js`). A branch atual de cada projeto vem de um `git rev-parse`
  por ciclo; o `ragx status --json` completo roda só para o projeto aberto.
- **Economia estimada e segurança** continuam como no v1 (chamadas diretas,
  fora da fila).

### Testes da Parte B

- Fila: serial, cancelamento, previsão, erro com as últimas linhas do log.
- Checagens de conexão com `child_process` e HTTP simulados: cada estado e
  cada motivo.
- IPC: id desconhecido é recusado; nenhuma ação aceita caminho vindo do
  renderer.
- Descoberta de projetos: profundidade, pastas puladas.
- Telas: card por estado, filtro, detalhe, onboarding.
- Verificação visual com screenshots do app real via Playwright/Electron,
  como na revisão do v1.

## Ordem

1. Parte A, com plano próprio.
2. Parte B, com plano próprio, depois da A em `main`.
3. Parte C (travessões), spec separada depois de decidir o escopo.
