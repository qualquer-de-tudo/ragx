# Changelog

Formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
versionamento [SemVer](https://semver.org/lang/pt-BR/).

> **Regra deste arquivo:** toda alteração relevante atualiza o CHANGELOG na
> MESMA alteração que a produz. Deixar para depois é como uma correção some do
> histórico — quem a escreveu lembra do porquê; a próxima pessoa, não.

## [Não lançado]

### Adicionado

- **Telemetria de chamadas MCP gravada em `.ragx/logs/mcp.jsonl`** — cada
  ferramenta MCP registra um JSON line com `ts`, `tool`, `ms` (latência),
  `project` e (para `build_context` apenas) `tokens_delivered`. Queries e
  argumentos nunca são gravados, evitando que a telemetria vire um log do que
  o time está perguntando sobre o próprio código.

- **Registro automático no hub durante `ragx init`** — o projeto é registrado
  best-effort; falhas (projeto privado, colisão de nome) nunca fazem `init`
  falhar. Projetos que predatam essa mudança, ou marcados `private` que o
  usuário depois quer registrar com visibilidade diferente, continuam usando
  `ragx project register`.

- **Painel desktop (Electron)** — aplicativo local, sem login, que mostra por
  projeto registrado no hub: contagem de documentos/chunks/embeddings,
  telemetria de chamadas MCP (tokens reais entregues), economia estimada sob
  demanda (via `ragx trial`) e achados de segurança sob demanda (via
  `ragx security scan`). Atualiza por polling a cada 5s; instalador `.exe`
  gerado com `electron-builder`.

  A lista lateral compara o tamanho do índice entre projetos e mostra onde
  cada um mora (dois projetos chamados `src` deixam de ser indistinguíveis).
  O painel avisa quando há chunks sem embedding — nesse caso a busca semântica
  cai para só palavra-chave, o que antes passava despercebido — e o scan lista
  os arquivos bloqueados com severidade e regra, sem exibir o trecho do
  segredo. O tema é sempre escuro, com fundo preto; não muda mais com o tema
  do Windows.

  A janela abre com fundo preto e título "RAGX Painel". Fechar o painel com
  alguma tarefa em andamento pergunta antes de cancelar todas elas.

  Cada card agora lê `.ragx/status.json` e a branch/commit atuais do git para
  dizer o estado real do projeto: "Atualizado", "Defasado" (branch ou commit
  mudou desde a última indexação), "Embeddings faltando", "Sem hooks", "Com
  problema" ou "Pasta ausente" — em vez de só "ok"/"degradado".

- **O índice acompanha a branch.** Cada indexação registra branch, commit e quem
  disparou (`cli`, `panel`, `watch`, `sync`, `mcp:*`, `hook:*`). `ragx status --json`
  diz se o índice está defasado e por quê (troca de branch, commits novos,
  arquivos alterados depois da indexação, embeddings pendentes) e traz as
  últimas 10 indexações. `ragx hooks install` (ou `ragx init --git-hooks`) liga
  hooks de `post-checkout`, `post-commit` e `post-merge` que reindexam em
  segundo plano. Só uma indexação roda por vez (`.ragx/index.lock`); pedidos
  que chegam no meio ficam agendados. O estado de cada projeto fica em
  `.ragx/status.json`, e `ragx index --progress` emite progresso em JSON.

  A trava (`.ragx/index.lock`) protege `ragx index` — `mcp:index`/`mcp:sync`
  respondem `busy` estruturado nesse caso, em vez de um falso `internal` — mas
  ainda **não** cobre `ragx sync`, `ragx graph rebuild` nem
  `ragx dictionary generate`. Um pedido de `ragx sync` que chega ocupado
  reagenda só a reindexação incremental; knowledge/, grafo, dicionário e
  federação não são refeitos automaticamente quando ela libera — a CLI avisa
  isso explicitamente em vez de prometer "o pedido ficou agendado" (mensagem
  genérica, certa para `index`, enganosa aqui). Rodar `ragx sync`,
  `ragx graph rebuild` ou `ragx dictionary generate` ao mesmo tempo que uma
  indexação disparada por hook pode, raramente, gerar dois escritores;
  cobertura completa da trava para os três fica para uma tarefa futura.

### Corrigido

- `ragx mcp install` voltou a funcionar. O pacote `ragx.clients` tinha se perdido
  num merge e o comando (e os instaladores, que o chamam) quebrava com
  `ModuleNotFoundError`.

## [1.0.0-beta.3] — 2026-09-17

### Corrigido

- **A métrica `nDCG@10` estava errada e podia passar de 1,0** (`RAGX-0098`).
  Ela contava caminhos duplicados como acertos separados, com o denominador
  ideal contado em arquivos: `_ndcg(['a','a','a'], ('a',))` devolvia **2,131**
  numa métrica cuja definição tem teto 1,0.

  O erro tinha direção, e é isso que o tornava caro: **premiava devolver o
  mesmo arquivo picado em vários chunks** — o oposto de um contexto bom. Quem
  otimizasse contra ela estaria otimizando para fragmentar o resultado.

  O ganho passa a ser contado uma vez por documento, na posição em que ele
  aparece pela primeira vez. **Os valores mudam**: nDCG cai de 0,76 para 0,48
  (keyword), 0,66 para 0,44 (semantic) e 0,76 para 0,49 (hybrid). A série
  histórica quebra porque os valores antigos estavam inflados.

### Adicionado

- **Camada do documento: conhecimento, registro de trabalho ou teste**
  (`RAGX-0102`). Um repositório não guarda só conhecimento — guarda também o
  registro de como ele foi construído. Medido aqui: `task/` é **22% dos
  chunks**, mais que toda a documentação, e vencia o código na busca. Para
  *"como o security gate decide bloquear um arquivo"*, o primeiro fragmento era
  o enunciado da TAREFA que pediu para construir o gate.

  `ragx.tiers` classifica por caminho, configurável em `ragx.toml`:

  ```toml
  [index]
  work_paths = ["task/", "adr-drafts/"]
  test_paths = ["tests/"]

  [search]
  weight_tier_work = 0.45
  weight_tier_test = 0.7
  ```

  **Pesa, não exclui** — às vezes a resposta está mesmo na tarefa, e há teste
  fixando que ela continua encontrável. A classificação acontece na LEITURA, e
  não numa coluna do banco: mudar `work_paths` passa a valer sem reindexar.

  Efeito no conjunto de 26 consultas:

  | modo | recall@5 | MRR |
  |---|---|---|
  | keyword | 0,77 → **0,81** | 0,47 → **0,62** |
  | semantic | 0,54 → **0,69** | 0,44 → **0,51** |
  | hybrid | 0,62 → **0,77** | 0,51 → **0,59** |

  > Os `relevant_paths` do conjunto nunca apontam para `task/` ou `tests/`, então
  > rebaixar essas camadas melhora a métrica **em parte por construção**. O ganho
  > é real no sentido de que o conjunto encoda julgamento humano sobre onde a
  > resposta mora — e precisa ser confirmado com casos cuja resposta esteja numa
  > tarefa, o que entra na `RAGX-0099`.

### Adicionado

- **`ragx eval` passa a reportar o intervalo de confiança** (`RAGX-0100`):

  ```text
  Modo          Recall@5          IC 95%      MRR   nDCG@10
  keyword           0.77     [0.58–0.89]     0.47      0.48
  semantic          0.54     [0.35–0.71]     0.44      0.44
  hybrid            0.62     [0.43–0.78]     0.51      0.49

  ! O intervalo de confiança chega a 0.36 de largura com n=26.
    Acima de 0.20 o conjunto não distingue os modos.
  ```

  Wilson, não o intervalo normal: com n pequeno e proporção perto de 0 ou 1, o
  normal escapa de [0,1] e mente sobre a precisão. O aviso vem **antes** do
  veredito ✓/✗, e o veredito sai marcado como inconclusivo enquanto o conjunto
  não distinguir os modos — foi lendo o número sozinho que "0,62 contra 0,77"
  virou a afirmação publicada de que a busca híbrida falhou o critério.

### Desempenho

- **O embedder passa a ser construído uma vez por processo** (`RAGX-0097`).
  `build_embedder()` era chamado a CADA busca semântica — e mais uma vez dentro
  do `build_context`. Construir o modelo ONNX custa 2537–3638 ms; embutir a
  consulta com ele pronto custa 6–27 ms. Ou seja: ~99% da latência da busca
  semântica era carregar o modelo de novo.

  | | antes | depois |
  |---|---:|---:|
  | `search --mode hybrid` (2ª chamada no mesmo processo) | 2677 ms | **58 ms** |
  | `build_context` (sem cache) | 5327 ms | **287 ms** |

  Nenhum resultado muda — há teste de contrato fixando que os `chunk_id`
  devolvidos são os mesmos, nos três modos. O ganho aparece em processo que
  vive: o servidor MCP, o `ragx watch` e a indexação. A diferença de 150× que
  havia entre `search keyword` (18 ms) e `search hybrid` não era propriedade de
  busca vetorial — era este defeito.

## [1.0.0-beta.2] — 2026-09-17

### Corrigido

- Regra de segurança `filename-deny:tokens` bloqueava `src/ragx/tokens.py` e um
  doc de tarefa da própria indexação do projeto — o padrão `**/tokens.*` casava
  com qualquer extensão. Restringido a extensões plausíveis de dump de segredo
  e a separador explícito antes de `token(s)`.

  A lista precisa resolve o caso de DADOS (`tokens.json`, `api_token.txt`
  continuam bloqueados), mas sozinha ainda derrubava `auth_token.py` e
  `refresh-token.go`, que casam em `**/*_token.*`. Junto dela entra
  `content_decides`: as regras que ADIVINHAM pelo nome (`tokens`, `secrets`,
  `credentials`, `password`) deixam de bloquear arquivos de código-fonte, que
  seguem para a fase 2 e têm o conteúdo lido por inteiro. As regras de FORMATO
  ou LOCAL (`*.pem`, `.ssh/**`, `.env`) continuam absolutas.

  O contrapeso é testado: um segredo real dentro de `tokens.py` continua
  bloqueado, agora pelo conteúdo. Quem afrouxar um lado sem o outro quebra
  `tests/security/test_filename_deny.py`.

- **O grafo aparecia sem nenhuma aresta na extensão do VS Code.** `get_entity`
  descrevia cada relação só como "o nó do outro lado" (`other`, `other_type`),
  sem dizer quem era origem e quem era destino. A extensão procurava
  `target`/`dst`, não encontrava e descartava a relação em silêncio: a tela
  mostrava os nós soltos, sem erro em lugar nenhum.

  `get_entity` passa a devolver também a aresta ORIENTADA (`src`/`dst`, os
  mesmos nomes da tabela `relations`), sem remover `other*` — que continua
  sendo a forma certa para uma lista de vizinhos. Verificado ponta a ponta:
  34 relações viram 34 arestas desenháveis, onde antes eram zero.

  Na `GraphEdge` a procedência viaja como `tier`, e não como `source`: o campo
  `source` da aresta é o nó de ORIGEM, e usar o mesmo nome para as duas coisas
  sobrescreveria a ponta da aresta.

- A lista de relações de uma entidade mostrava `?` em todo destino — o mesmo
  campo trocado, no mesmo lugar.

- `ragx graph show --json` não emitia `nodes`. A extensão filtrava as arestas
  contra um conjunto de nós vazio e descartava todas: o transporte de reserva
  também desenhava um grafo em branco.

- **A extensão podia subir dois processos RAGX.** Ativação, troca de pasta do
  workspace e mudança de configuração disparam conexão, e nada impedia que
  duas corressem juntas — só a última ficava referenciada, e a outra virava um
  processo Python órfão de ~100 MB. `conectar()` agora tem fila, e trocar de
  pasta só reconecta se a RAIZ do projeto mudar.

- **A queda do RAGX passava despercebida.** Crash do Python, pipe fechado ou
  `kill` de fora só apareciam na consulta seguinte, com um erro de transporte,
  enquanto a barra de status ainda dizia `Ready`.

- **A suíte de testes lia o `$HOME` da máquina.** `test_list_projects` esperava
  o projeto `demo` e recebia o primeiro projeto registrado no hub real de quem
  rodava — verde no CI, vermelho na máquina de quem usa o RAGX em mais de um
  projeto. Pior: um teste que lê o hub real também escreve nele.
  `tests/conftest.py` redireciona o HOME da sessão inteira.

### Adicionado

- macOS na matriz de CI (`ragx` e `instalador`) — o `install.sh` sempre se
  descreveu como suporte a Linux e macOS, mas nunca tinha rodado de verdade lá.
- `LICENSE` (MIT), `AGENTS.md` (onboarding de quem contribui no próprio RAGX)
  e `SECURITY.md` (canal de disclosure via GitHub Security Advisories).
- `ragx trial` — mede, no corpus de avaliação, quantos tokens o `build_context`
  economiza contra o baseline de ler o arquivo inteiro.
- Instalador agora também registra o servidor MCP em Cursor, Windsurf, Gemini
  CLI e Codex CLI — antes só Claude Desktop e Claude Code.
- **Reconexão com espera crescente.** Detectada a queda, a extensão reconecta
  sozinha em 1 s, 2 s, 4 s… até 60 s, com seis tentativas. Desligar de
  propósito não conta como queda, e "RAGX: Reconnect" zera o contador. Um RAGX
  não instalado falha em ~50 ms; sem a espera, isso era um laço de `spawn` a
  100% de CPU.
- **Medição de cada etapa da conexão**, numa linha do log. É o que transforma
  "o RAGX está lento" em um número, sem profiler.
- `vscode-plugin/scripts/bench-connect.mjs` — benchmark do caminho real de
  conexão, com mediana de cada etapa.
- A versão que a extensão anuncia ao servidor MCP passa a ser injetada pelo
  esbuild a partir do `package.json`. Era um literal em `McpClient.ts`, e
  mantê-los em dia dependia de lembrar de bumpar dois arquivos no mesmo commit.

### Desempenho

- **Imports pesados saíram do topo dos módulos de comando.** `cli/main.py`
  importa os 21 módulos de comando só para registrá-los, e cada um carregava
  seu subsistema junto: `ragx --version` puxava numpy, o motor de contexto e o
  avaliador de agentes. Medido com `python -X importtime`:

  | | antes | depois |
  |---|---:|---:|
  | `ragx --version` | 882 ms | 523 ms |
  | `ragx documents --limit 5` | 1086 ms | 597 ms |
  | `ragx entities --limit 5` | 938 ms | 537 ms |
  | `import ragx.cli.main` | 899 ms | 484 ms |

  Vale para toda invocação da CLI, inclusive o transporte de reserva da
  extensão, que roda um processo por consulta.

- **Conexão VS Code → RAGX: 1747 ms → 1482 ms** (mediana de 7 rodadas, -15%).

  O ganho é modesto de propósito, e a medição explica por quê: **mais de 98% do
  tempo é boot de processo Python**, e ~1,4 s disso é o import do SDK de MCP,
  que é de terceiros e constrói os modelos de todas as versões do protocolo.
  Transporte, handshake e consultas somam ~15 ms — não há nada a ganhar ali.

  Por isso o trabalho de desempenho foi para **não pagar esse custo duas
  vezes** (fila de conexão, reconexão só quando a raiz muda de verdade) em vez
  de perseguir os milissegundos que já eram baratos.

### Documentado

- `docs/09-mcp.md` agora cobre as 33 ferramentas MCP reais — as 13 de
  orquestração de tarefas (Fase 13) nunca tinham sido documentadas no contrato
  formal. E `tests/unit/test_documentacao_mcp.py` compara as ferramentas
  registradas com as documentadas **nos dois sentidos**, para que a divergência
  quebre a suíte em vez de envelhecer calada.
- `docs/README.md` não trava mais números de "estado atual" (documentos,
  entidades) que ficavam desatualizados sem aviso — aponta para `ragx doctor`.
- `docs/06-grafo.md` documenta o contrato de uma relação: as duas leituras da
  mesma aresta, `confidence`, `tier` e por que os dois formatos convivem.
- `docs/22-vscode-e-desempenho.md` — o caminho completo da conexão, onde o
  tempo vai, prontidão, reconexão, diagnóstico e o que foi deliberadamente
  **não** feito, com o motivo.

## [1.0.0-beta.1] — 2026-09-16

Relançamento. As releases **1.0.0, 1.0.1 e 1.0.2 foram retiradas**: saíram
enquanto o repositório era privado, e todas as instruções de instalação delas
partiam dessa premissa. O repositório agora é público, o caminho de instalação
mudou, e manter releases que ensinam o caminho errado é pior do que não ter
release nenhuma.

Nada foi perdido: esta beta reúne tudo o que as três traziam, com o histórico
de cada correção preservado abaixo. O número volta a `1.0.0-beta.1` porque é o
que a maturidade honesta do projeto comporta — veja as ressalvas no fim.

### Mudado

- **Instalar voltou a ser um comando.** Com o repositório público, o
  `curl | bash` e o `irm | iex` funcionam de novo: o instalador cai no caminho
  `git+`, que até aqui nunca tinha sido exercitado porque o clone anônimo
  falhava por credencial. Verificado de ponta a ponta com `UV_TOOL_DIR`
  isolado — instala e responde com as 33 ferramentas MCP.

  Continua valendo baixar os arquivos da release: é o único caminho que traz a
  **extensão do VS Code** junto, e o único que prega uma versão exata.

### Corrigido

- **O instalador do Linux abortava mudo, com código 2.** `instalar_extensao`
  procura o `.vsix` com `ls -1 "$pasta"/*.vsix | sort -r | head -1`. Sem
  correspondência o `ls` sai com 2, o `pipefail` propaga isso pelo pipe, a
  atribuição herda o status e o `set -e` mata o script — **depois** de já ter
  instalado o RAGX, configurado o PATH e registrado o MCP, e sem imprimir uma
  linha de erro. O job de instalação do CI em Ubuntu vinha caindo assim desde
  que a função foi introduzida.

  `encontrar_wheel` tem o mesmo padrão e escapou por acidente: é chamada dentro
  de um `elif`, onde o `set -e` fica suspenso. As duas passam a terminar em
  `|| true`, porque depender do ponto de chamada é armadilha para quem mexer
  depois.

  A instalação a partir dos arquivos de uma release **não** era afetada: com o
  `.vsix` na pasta, o `ls` encontra algo e não falha. Quem instalava de um
  clone do repositório, sim.

- **O instalador agora diz onde parou.** Uma parada silenciosa foi o que fez o
  bug acima sobreviver a um ciclo de release: no log, três linhas de sucesso e
  então `exit code 2`. O script ganhou `set -E` e um `trap ... ERR` — sem o
  `-E` o trap não vale dentro de função, que é justamente onde a falha
  acontecia. Agora a saída é `✗ o instalador parou na linha N (codigo 2)`.

  O `install.ps1` não tem o problema: usa `Get-ChildItem -ErrorAction
  SilentlyContinue`, que devolve vazio em vez de lançar.

- **A extensão pedia mais resultados do que o RAGX aceita.** O `SearchRequest`
  do servidor limita `limit` a 50 e **recusa** acima disso — não trunca. O
  inventário de documentos pedia 100 quando caía na derivação por busca, e a
  aba inteira respondia `search_hybrid falhou: ValidationError`. O teto do
  servidor agora é uma constante no cliente (`MAX_SEARCH_LIMIT`), aplicada
  dentro do `search()`, de modo que **todo** chamador fica coberto — não só o
  que estourou desta vez.
- **`ValidationError` virava `internal`.** Argumento fora do contrato é erro de
  quem chamou, não falha interna do servidor. Tratá-lo como `internal`
  produzia "`<ferramenta>` falhou: ValidationError. Detalhe em
  `.ragx/logs/errors.log`" — uma mensagem que manda caçar num traceback o que
  ela mesma poderia dizer. Agora o código é `invalid_argument` e a mensagem
  nomeia campo, limite e valor recebido:

  ```text
  search_hybrid: `limit` input should be less than or equal to 50 (recebido: 100)
  ```

- **A extensão não tinha texto para dois códigos de erro.** `invalid_argument`
  e `unsupported` caíam no ramo padrão e apareciam como "Falha ao falar com o
  RAGX", que culpa o transporte por um erro de chamada ou por uma instalação
  velha. Cada um tem agora título próprio; o de `unsupported` traz o comando de
  atualização.

### Notas

- **O wheel da 1.0.0 que chegou a circular foi construído antes de
  `list_documents` existir.** Instalações a partir dele caem na derivação por
  busca, que é o caminho degradado. Como aquela release foi retirada, o
  problema some com ela — mas se você instalou de um wheel `1.0.0` baixado
  antes, reinstale.
- Ferramenta e extensão passam a andar no mesmo número: `1.0.0-beta.1`.
- As notas de release e os dois READMEs foram reescritos para o repositório
  público: comando único primeiro, download da release como o caminho que
  prega a versão e traz a extensão.

### Adicionado

- **GitHub Actions**: `ci.yml` roda testes em Ubuntu e Windows, Python 3.11 e
  3.12, mais o build do plugin e a **instalação de ponta a ponta** nos dois
  sistemas. `release.yml` constrói e publica com a tag.
- **`scripts/release.py`** — gera wheel, sdist, `.vsix`, instaladores e
  `SHA256SUMS.txt` em `release/`, num comando, nos três sistemas.
- **`.gitattributes`** — `.sh` sempre com LF, `.ps1` com CRLF. Sem isto, o
  `core.autocrlf` do Windows grava CRLF no instalador e o Linux responde
  `bad interpreter: No such file or directory`, que não diz nada sobre a causa.

### Registro do MCP: dois bugs de corrupção de configuração

Encontrados registrando o servidor de verdade nesta máquina. Escrever no
arquivo de configuração de outro programa é a operação mais perigosa que o
instalador faz, e as duas falhas eram silenciosas:

- **`Set-Content -Encoding utf8` grava COM BOM** no PowerShell 5.1, e o
  `JSON.parse` do Node — que é quem lê esses arquivos — lança exceção ao ver
  BOM. O `claude_desktop_config.json` ficou com o conteúdo certo e ilegível
  para o cliente. Agora usa `WriteAllText` com `UTF8Encoding($false)`.
- **`ConvertFrom-Json '{}'` devolve `$null`** no PS 5.1. O código chamava
  `.PSObject` nele, estourava, e gravava um arquivo **vazio** — apagando os
  outros servidores MCP da pessoa sem avisar. Agora a conversão passa por uma
  tabela hash que trata nulo, dicionário e objeto.

Verificado em cinco formatos de config: inexistente, vazio, `{}`, com outro
servidor, e com um `ragx` anterior. Em todos, as chaves de topo, os outros
servidores e os dados de projeto foram preservados.

O registro passou a usar o **caminho absoluto** do executável: aplicativo
gráfico não herda o PATH do usuário de forma confiável, e `ragx` sozinho pode
não ser encontrado pelo cliente.

### Pasta sem projeto não é falha interna

Com o servidor MCP registrado globalmente, ele sobe em toda sessão — inclusive
onde não existe projeto RAGX. A busca respondia `internal` e mandava olhar
`.ragx/logs/errors.log`, que não existe ali. O agente concluiria que o RAGX
está quebrado e pararia de consultá-lo.

Agora responde `not_indexed`, dizendo o que fazer: rodar `ragx init` se for o
projeto certo, ou abrir a sessão dentro de um projeto já indexado.

### Instalação a partir dos arquivos baixados

> Escrito quando o repositório ainda seria privado. O comando único voltou a
> funcionar (veja **Mudado**, no topo); o que está abaixo continua valendo como
> o caminho que prega uma versão e traz a extensão do VS Code.

O instalador faz o resto sozinho:

- **encontra o `ragx-*.whl` sozinho**, na pasta do próprio script, na pasta
  atual ou em `~/Downloads`. O wheel vem ANTES do clone na ordem de busca:
  quem baixou os arquivos de uma release quer AQUELA versão, não o que
  estiver no `main` hoje.
- **encontra o `.vsix` e instala a extensão**, se o `code` estiver no PATH.
  Sem ele, imprime o comando em vez de falhar — muita gente usa outro editor.
- `RAGX_ORIGEM` / `-Origem` continua disponível para apontar um caminho.
- `RAGX_INSTALL_VSCODE=0` / `-SemVsCode` pula a extensão.

Corrigido junto: **o instalador saía com código != 0 mesmo dando certo.** O
`ragx doctor` sai diferente de zero enquanto não existe índice — o que é
esperado numa instalação nova — e esse código vazava como resultado do script.
Qualquer automação concluiria que a instalação falhou depois de ela ter dado
certo.

Verificado nos dois sistemas simulando o download de verdade: os cinco assets
numa pasta, terminal aberto ali, um comando. Saída 0 em ambos.

### Corrigido depois de tentar o comando único de verdade

O `irm ... | iex` não instalava. Três camadas de falha, empilhadas:

1. **TLS.** O PowerShell 5.1 negocia TLS 1.0 por padrão e o GitHub recusa. O
   erro é `A conexão foi fechada de modo inesperado`, que não menciona TLS. O
   comando documentado agora traz a linha que ajusta isso — ela não é opcional.
2. **Encoding.** O `Invoke-RestMethod` não recebe charset num asset de release
   (`application/octet-stream`) e decodifica o corpo como Latin-1. Com acentos,
   o script chegava corrompido e o parser cuspia dezenas de "Token inesperado".
   O `install.ps1` passou a ser **ASCII puro, sem BOM** — o oposto da regra
   anterior, que existia para a leitura em disco.
3. **Execução por pipe.** Sem arquivo em disco, `$PSScriptRoot` e
   `${BASH_SOURCE[0]}` vêm vazios. Os dois instaladores morriam ao derivar a
   raiz do repositório. Agora detectam a ausência do arquivo antes de usá-la.

Também: o `install.ps1` deixou de usar `exit` — por `iex` ele roda dentro da
sessão de quem chamou, e `exit` fecharia o terminal da pessoa no meio do
trabalho. Falha virou `throw`, com a mensagem impressa e a sessão intacta.

Novo: `RAGX_ORIGEM` / `-Origem` para instalar de um wheel baixado, sem clone e
sem acesso ao repositório.

Verificado servindo os scripts por HTTP e rodando `irm | iex` neste Windows e
`curl | bash` num container Ubuntu 24.04.

### Corrigido depois da primeira execução do workflow

Os dois jobs de instalação falharam na primeira tentativa. As duas causas eram
do workflow, não do produto:

- **`python` não é garantido no runner.** O passo que conferia se o segredo
  entrou no índice usava `python -c` para contar resultados. A contagem agora
  usa `grep -c '"chunk_id"'`, que não depende de interpretador nenhum.
- **`$HOME/.local/bin` no Windows.** Em bash, `$HOME` vira `/c/Users/...`, e o
  PATH do Windows não entende esse formato — o `ragx` não era encontrado no
  passo seguinte. O diretório agora vem de `uv tool dir --bin`, que devolve o
  caminho nativo de cada sistema.

Os dois passos foram reproduzidos localmente antes de subir: num container
Ubuntu 24.04 sem Python instalado, e neste Windows.

As ações também subiram de versão (`checkout@v5`, `setup-uv@v6`,
`setup-node@v5`, `upload/download-artifact@v5`) — o runner já forçava Node 24 e
avisava a cada execução.

### Verificado na publicação

O workflow de release **não publica antes de testar**. Ele instala a partir do
wheel recém-construído, nos dois sistemas, roda o ciclo completo num projeto
novo e confere que um `.env` com credencial não entra no índice. Se entrar, o
build quebra ali — não na máquina de alguém.

### Ressalva que continua valendo

A busca híbrida ainda não supera a busca por palavra-chave neste corpus
(recall@5 0,65 contra 0,77). O critério documentado `híbrida > semântica >
keyword` não foi atingido, e o diagnóstico com evidência está em
`docs/05-busca.md`. Trate a busca como auxílio à descoberta, não como fonte
única de verdade.

## [0.3.1] — 2026-09-15

Instalação de verdade e interface visual.

### Adicionado

- **Extensão do VS Code** `ragx-knowledge-explorer` 1.0.0-beta.1
  ([vscode-plugin/](vscode-plugin/README.md)) — busca semântica, grafo
  navegável com expansão progressiva, dicionário, Context Builder, monitor e
  status de segurança, dentro do editor. React + Tailwind sobre as variáveis de
  tema do VS Code: Light, Dark e High Contrast saem de graça.
- **Instaladores** para Windows (`install/install.ps1`) e Linux/macOS
  (`install/install.sh`). Colocam o `ragx` no PATH, registram o servidor MCP e
  **verificam** o resultado.
- Extra `all` no pacote: servidor MCP, busca semântica e contagem de tokens.

### Corrigido

Três bugs de instalação achados testando os instaladores de verdade — o do
Windows neste Windows, o do Linux num container Ubuntu 24.04:

- **`uv` escolhia Python 3.10** e o RAGX usa `StrEnum` (3.11+). A falha
  aparecia depois, como `ModuleNotFoundError: pydantic_core._pydantic_core`,
  longe da causa. `--python` agora é explícito.
- **`ragx mcp serve` falhava após instalar com sucesso**: o pacote `mcp` era um
  extra que o instalador não pedia. Servir agentes por MCP é o propósito do
  RAGX, não um acessório — daí o extra `all`.
- **PowerShell 5.1** (padrão do Windows) tratava o stderr do `uv` como exceção
  e lia o `.ps1` sem BOM como ANSI. Corrigido com um helper para chamada nativa
  e BOM no arquivo.

Há testes para os três: `tests/unit/test_documentacao.py` verifica que o extra
`all` carrega `mcp`, que os instaladores fixam o Python e registram o MCP, e
que o `.ps1` tem BOM.

No plugin, dois bugs achados pelos próprios testes:

- `humanize()` ecoava a mensagem crua do RAGX — um traceback de Python chegaria
  à tela, exatamente o que a §39 do pedido proíbe.
- `isBlocked()` só olhava a raiz do objeto; um resultado de busca com marcação
  de bloqueio dentro de `content` passava direto para a UI.

### Segurança

- A webview roda sob CSP restrita: sem `eval`, sem script inline,
  `connect-src 'none'`. Nenhum `dangerouslySetInnerHTML`.
- A lista de arquivos bloqueados **nunca** chega à tela — só a contagem
  agregada por regra. A agregação acontece no cliente, antes da webview.
- Zero rede, zero telemetria, zero CDN: a extensão empacota tudo que usa.

## [0.3.0] — 2026-09-15

Task Analyzer e orquestração. O RAGX deixa de só responder perguntas e passa a
decidir **se vale executar agora ou documentar e decompor antes** — e a manter
a fila de trabalho que sai disso. Fase 13 em
[`task/fase-13-task-analyzer-orquestracao/`](task/fase-13-task-analyzer-orquestracao/).

### Adicionado

- **Task Analyzer** (`ragx task analyze`) — classifica toda solicitação em 7
  dimensões e decide a estratégia. Determinístico e offline: sinais declarados
  em `signals.yaml`, mais duas dimensões **medidas no índice real** (quantos
  módulos já tocam o assunto, e se existe documento cobrindo). Ver
  [docs/20](docs/20-task-analyzer.md).
- **Documentation Planner** — decide QUAIS documentos o trabalho exige, em
  ordem topológica entre 15 tipos, e produz esqueletos já fundamentados no
  conhecimento existente. Lacuna vira `> **Pendente:**` explícito; o RAGX não
  inventa texto.
- **Task Decomposer** — 12 trilhas (análise, documentação, banco, backend,
  frontend, integração, testes, segurança, performance, deploy,
  observabilidade, validação) com DAG, critérios de aceite e escopo de arquivos
  derivado do grafo.
- **Banco de orquestração** `.ragx/ragx.sqlite` — 18 tabelas, máquina de
  estados com 11 estados, lease atômico, retry com backoff. Separado do
  `knowledge.db` ([ADR-0014](docs/adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md)).
- **Dispatcher e validação** — `claim`/`report`/`release` com contexto montado
  por tarefa; validação determinística (escopo, evidência, gate), sem juízo
  sobre qualidade de código.
- **Worker e scheduler** — `ragx worker` para cron; parser de cron de 5 campos
  sem dependência nova; agendamento `once|cron|interval|dependency|event|manual`.
- **13 ferramentas MCP novas** — `analyze_request`, `plan_work`, `claim_task`,
  `report_task_result`, `release_task`, `next_task`, `list_tasks`, `get_task`,
  `task_graph`, `task_status`, `set_task_status`, `add_task_dependency`,
  `run_worker`. Total: 32.
- **Board versionado** — `knowledge/tasks/` viaja no Git; execução não.
  Conflito de `status` resolve por precedência declarada.
- `ragx task` (17 subcomandos), `ragx worker`, `ragx schedule` (5 subcomandos).

### Alterado

- `ragx sync` reidrata o board de tarefas antes de regravá-lo, e **avisa**
  quando o histórico de execução local não voltou.
- `docs/09-mcp.md` e `docs/roadmap.md` atualizados com a fase 13.

### Segurança

- O contexto entregue ao agente vem do índice, que não contém segredo —
  verificado por teste com um `.env` real no projeto de teste.
- `ragx.tasks` entrou na lista de módulos que leem artefatos próprios, com um
  teste novo garantindo que ele **não varre o projeto**: `rglob`, `walk`,
  `scandir` e `read_bytes` são proibidos ali. O teste já pegou um `glob` em
  `docs/adr/` no planner, trocado por consulta ao índice.
- As invariantes do ADR-0006 seguem verificadas e não relaxadas.

### Notas de desenho

- O RAGX **não executa** a tarefa. Ele é a fila e o árbitro; quem executa é o
  agente conectado por MCP
  ([ADR-0015](docs/adr/ADR-0015-quem-executa-a-tarefa.md)). Embutir um cliente
  de LLM traria rede e credencial para dentro de um sistema cujo argumento é
  rodar offline.
- Pedido trivial **não** vira projeto. Metade do valor do analisador está em
  não criar burocracia: typo, renomear variável e ajuste visual continuam
  sendo execução direta.

## [0.2.0] — 2026-09-15

Autonomia do agente e conhecimento compartilhado entre projetos. Fase 12 em
[`task/fase-12-autonomia-e-conhecimento-base/`](task/fase-12-autonomia-e-conhecimento-base/).

### Adicionado

- **Conhecimento base** (`ragx base`) — fontes externas de regras, baixadas uma
  vez por máquina em `~/.ragx/base/`, indexadas sob `@base/<fonte>/` em cada
  projeto que as **declara** em `[base] sources`. Conteúdo de terceiro passa
  pelo mesmo Security Gate; `knowledge/base.json` carrega a receita (origem,
  ref, commit), não os arquivos. Ver
  [ADR-0013](docs/adr/ADR-0013-conhecimento-base-compartilhado.md).
- **`ragx watch`** — o índice acompanha o working tree por polling de
  `size+mtime`, com debounce e duas velocidades (reindexa a cada mudança,
  consolida a cada N). Zero dependência nova.
- **Escrita no índice via MCP** — `refresh`, `reindex`, `sync`,
  `rebuild_graph`, `generate_dictionary`, `base_sync`, `publish_contract`.
  Habilitadas por padrão em `ragx mcp serve`; `--read-only` desliga. Ver
  [ADR-0012](docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md).
- **`get_playbook`** — procedimento operacional que o agente lê uma vez:
  ordem das ferramentas, quando reindexar, e o que o índice deliberadamente
  não faz.
- `list_base_sources` no MCP.
- `ragx.walk.scan_fingerprints` — enumeração sem abrir arquivo, para o watcher.
- Testes de documentação: todo comando da CLI documentado, todo link relativo
  resolvendo.

### Alterado

- **`ragx` é o comando primário**; `rag` continua funcionando como alias
  histórico. 417 ocorrências em documentação, 85 em código.
  [ADR-0007](docs/adr/ADR-0007-nome-do-binario.md) revisado.
- `iter_files` aceita `prefix`, para namespaciar uma árvore no índice sem que o
  gate deixe de ver o caminho real.
- Serialização de `knowledge/` exclui `@base/` de documentos, chunks,
  embeddings, entidades e relações.
- `docs/09-mcp.md` não diz mais que "indexação é operação de CLI, não de
  agente" — a decisão foi revista, com o motivo registrado.

### Corrigido

- `publish_contract` chamava `hub.push`, que não existe (é `hub.sync`), e
  `generate_dictionary` tratava um `DictionaryReport` como dict. Ambos achados
  por um cliente MCP real, não pela suíte — que agora exercita **toda**
  ferramenta de escrita, parametrizada, para que ferramenta nova nasça coberta.
- `docs/06-grafo.md` e `docs/14-cli.md` documentavam `ragx graph <entidade>`;
  o comando real é `ragx graph show <entidade>`.

### Segurança

- Conteúdo de fonte base entra por `iter_files` → `SecurityGate.admit`, igual
  ao código do projeto. Teste garante que `ragx.base` nunca chama `read_bytes`
  nem `open`.
- Fonte instalada mas **não declarada** pelo projeto não é indexada — evita que
  um `ragx base add` mude em silêncio o índice de todos os projetos da máquina.
  A regra nasceu de sete testes que quebraram exatamente assim.
- As invariantes do ADR-0006 seguem verificadas e **não foram relaxadas**: o
  pacote `ragx.mcp` continua sem `open`, sem `pathlib`, sem rede, e abrindo o
  banco só em leitura.

## [0.1.0] — 2026-09-15

Primeira versão. MVP completo das 12 fases planejadas em [`task/`](task/).

### Segurança

- `SecurityGate` entre o leitor de arquivos e o parser: nenhum componente fora de
  `ragx.security` recebe bytes que não tenham passado por `admit()` (ADR-0008).
- 28 regras declarativas em YAML — auditáveis sem ler Python.
- Deny-list por nome de arquivo avaliada **antes** de qualquer leitura.
- Detecção em conteúdo: padrões de provedor, atribuição + entropia de Shannon,
  allowlist de placeholder e ajuste de severidade por contexto.
- `Redactor`: o valor do segredo nunca é persistido, logado ou impresso.
- `safe_echo`: entrada do chamador que pareça segredo volta mascarada — evita que
  uma query com a chave da AWS seja ecoada em mensagem de erro ou cabeçalho.
- Suíte de **8 superfícies** de vazamento (database, embeddings, graph, mcp,
  export, knowledge, federation, hub) — zero `xfail`.
- Testes arquiteturais: MCP sem filesystem/rede, só dois módulos leem o
  projeto-alvo, `core` não importa infraestrutura.

### Indexação

- Chunking estrutural por AST (Python) e por heading (Markdown); JSON, YAML,
  TOML, XML e SQL por estrutura nativa; fallback por parágrafo.
- IDs determinísticos e estáveis entre Windows e Linux.
- Indexação incremental com atalho por `size`+`mtime` e cache de embeddings.
- Transação por lote: `Ctrl+C` deixa o banco consistente.

### Busca e contexto

- Busca semântica em dois estágios (int8@256 grosseira → float32 rescoring),
  keyword FTS5/BM25 com pesos por coluna, fusão RRF.
- Grafo de conhecimento em duas camadas determinísticas, sem LLM.
- Context Engine: dedup literal/quase-duplicata/MMR, compressão extrativa em
  quatro estratégias, orçamento com reserva por fonte e `--explain`.

### Colaboração

- `knowledge/` versionado sem conteúdo de chunk (reidratado e conferido por hash)
  e com embeddings int8 shardados por prefixo de ID (ADR-0010).
- `ragx sync` com delta por Git e fallback por hash.
- Pacote `.rag` com re-scan obrigatório, verificação de integridade, checksums,
  proteção contra zip-slip e matriz de compatibilidade.

### Multiprojeto

- Fatia de federação versionada e autossuficiente: contratos por valor.
- Hub local agregando N projetos, clonados ou só pela fatia.
- Resolução de vínculos `consumes` ⟷ `provides` com normalização de rota entre
  stacks; consumo sem provedor e divergência de método são reportados.
- Busca cross-project com `--scope all` e atribuição obrigatória de `project`.

### Agentes

- Servidor MCP com 10 ferramentas, casca fina sobre a API interna (ADR-0006).
- Perfis de agente versionáveis; regras curadas à mão preservadas no retreino.
- `ragx agent eval` mede recuperação — não geração, e diz isso.

### Conhecido

- A qualidade da busca semântica **não está validada**: sem Ollama na máquina de
  desenvolvimento, os testes usam o provider `hashing`, de qualidade semântica
  nula. Ver `task/fase-02-busca/RAGX-0031-*.md`.
- Camada semântica do grafo (`--semantic`) e enriquecimento do dicionário por LLM
  ainda não implementados — ambos opt-in por design.
