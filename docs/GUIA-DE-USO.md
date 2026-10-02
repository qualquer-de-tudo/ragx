# Guia de uso do RAGX

Este guia acompanha o instalador do painel (`RAGX-Painel-Setup-<versão>.exe`).
Ele leva você de "baixei o instalador" até "meu agente está consultando o
índice do meu projeto".

## O que é o RAGX

Um Knowledge Engine **local** para projetos de software. Ele lê o seu
repositório, **barra segredos antes de indexar**, responde buscas e entrega ao
seu agente (Claude Code, por exemplo) só os trechos de que ele precisa, dentro
de um orçamento de tokens. Sem servidor, sem nuvem, sem chave de API.

```text
repositório  →  [Security Gate]  →  índice local  →  seu agente (via MCP)
```

O que ele bloqueia **não existe** no índice: nenhuma busca, ferramenta ou
agente consegue devolver um `.env` ou uma chave que o gate barrou.

## 1. Instalar

1. Execute `RAGX-Painel-Setup-<versão>.exe`.
2. O Windows SmartScreen vai mostrar **"O Windows protegeu o computador"**,
   porque o executável ainda não é assinado. Clique em **Mais informações →
   Executar assim mesmo**.
3. Escolha a pasta (ou aceite a sugestão) e conclua.

O instalador põe o **painel** e a **CLI `ragx`** (com o `uv` e o Python 3.12
embutidos). Você não precisa ter nada instalado antes. Se o Claude Code estiver
na máquina, o servidor MCP do RAGX já é registrado nele.

Para conferir que o arquivo é o publicado, compare o SHA-256 com o que está na
página da release:

```powershell
Get-FileHash .\RAGX-Painel-Setup-<versão>.exe -Algorithm SHA256
```

**Atualizar:** rode o instalador da versão nova por cima. Nada é perguntado e a
CLI não é removida.

## 2. Primeira abertura (configuração inicial)

Na primeira vez, o painel abre uma configuração em quatro passos:

1. **Como o RAGX funciona**: a explicação curta acima.
2. **Conexões**: o estado das três peças de que ele depende (veja a seção 5).
3. **Projetos**: escolha uma pasta; o painel lista os repositórios que encontrar
   dentro dela. Marque os que quer indexar.
4. **Indexar**: **Começar** enfileira a indexação dos projetos marcados.

"Pular configuração" só marca o passo como feito; você adiciona projetos depois.
A explicação do passo 1 fica sempre disponível na tela **Como funciona**.

## 3. As telas do painel

| Tela | Para que serve |
|---|---|
| **Projetos** | Um card por projeto: estado do índice, pasta, branch, quando foi indexado, economia de tokens. Um botão no card faz o que o estado pede. |
| **Detalhe do projeto** | Quatro abas: *Visão geral*, *Economia de tokens*, *Histórico* e *Manutenção*. |
| **Atividade** | O que os agentes e a CLI estão fazendo, ao vivo: chamadas MCP, sessões do Claude, comandos no terminal. Nunca mostra o texto da consulta. A lista é paginada (50 eventos ou 20 sessões por página). |
| **Conexões** | CLI, Claude Code e Ollama, com correção de um clique. |
| **Como funciona** | Fica no fim da barra lateral: o caminho do dado em cinco passos, o que mantém o índice em dia e onde ficam os dados. |

### Selos de estado de um projeto

| Selo | Significa | O que fazer |
|---|---|---|
| Atualizado | O índice bate com o código. | Nada. |
| Defasado | O código mudou depois da última indexação. | **Atualizar** no card. |
| Embeddings faltando | Há trechos sem vetor para a busca semântica. | **Gerar embeddings**. |
| Sem hooks | Os hooks de git não estão instalados. | Ligar o interruptor em *Manutenção*. |
| Com problema | A última indexação falhou. | Abra o detalhe e veja o motivo. |
| Pasta ausente | O projeto sumiu do disco. | Reaponte ou remova do hub. |
| Indexando… | Há uma tarefa rodando. | Aguarde; dá para cancelar no topo. |

### Adicionar um projeto

**Adicionar projeto** → escolha a pasta → marque os repositórios → confirme. Por
padrão o painel instala os **hooks de git**: o índice se atualiza sozinho a cada
commit, checkout e merge.

### Aba Manutenção

- **Atualizar agora**: indexação incremental.
- **Gerar embeddings faltantes**: completa só o que falta.
- **Reindexar do zero**: refaz tudo (pede um segundo clique).
- **Hooks de git**: liga e desliga a atualização automática.
- **Achados de segurança**: roda o `ragx security scan` e mostra o que o gate
  barraria.
- **Remover do hub**: tira da lista (segundo clique). **Nada é apagado do disco.**

### A fila

As tarefas rodam **uma de cada vez** (o Ollama é compartilhado). O indicador no
topo mostra quantas há, o progresso e a previsão, com **Cancelar** por tarefa.

### Atualizar o painel

Em **Preferências → Atualizações**, o painel confere o GitHub Releases ao abrir e a cada 6 horas. Achando uma versão
diferente da instalada, avisa **uma vez por versão**: notificação do sistema (o clique abre Preferências), um aviso na tela
e um ponto no item Preferências. Nada baixa sozinho: **Baixar atualização** e depois **Instalar e reiniciar** são cliques
seus. O instalador não é assinado, então o Windows pode mostrar o SmartScreen. Com a opção desligada, nenhuma chamada de rede.

## 4. Antes de indexar: veja o que será bloqueado

No terminal, dentro do projeto:

```powershell
ragx security scan .
```

Ele lista os arquivos que o Security Gate vai barrar (`.env`, chaves, tokens).
Confira antes de indexar um projeto novo. Se você rodar o scan no próprio
repositório do RAGX, vai ver segredos **falsos de propósito** nas fixtures de
teste: não são vazamento.

## 5. Conexões: as três peças

No topo da tela, o **Ajuste automático** mantém os hooks em dia sem você pedir: no Claude Code, o aviso de edição (o índice vê o
que o agente edita) e o lembrete de busca, em cada perfil onde o RAGX está ligado; no git, os hooks de cada projeto com índice.
Roda ao abrir o painel, a cada 15 minutos e quando aparece um projeto sem hooks. O interruptor desliga; **Ajustar agora** roda na hora.
Cada perfil do Claude mostra, em selos, quais hooks estão instalados. Quem recusou um hook por linha de comando
(`ragx claude on --no-touch`) continua com a escolha respeitada.

| Peça | Para que serve | Se não estiver verde |
|---|---|---|
| **RAGX CLI** | Roda tudo por baixo do painel. | **Instalar / Tentar de novo**. |
| **Claude Code** | Registra o servidor MCP do RAGX, para o agente usá-lo. | **Registrar para todos os projetos**. |
| **Ollama** | Gera os embeddings da busca semântica (modelo `nomic-embed-text`). | **Iniciar** e **Baixar nomic-embed-text**. |

O painel confere as três a cada 30 segundos; **Verificar agora** força uma
checagem.

**Ollama: Docker ou local.** O RAGX fala com `http://127.0.0.1:11434` (`localhost` é convertido: no Windows ele custava ~2 s por requisição), seja um
container ou uma instalação na máquina. O card mostra o modo detectado, o
processador (GPU ou CPU) e recomenda um modo com o motivo. **Medir velocidade**
mostra quantos chunks por segundo a sua máquina embeda. Em GPU AMD, prefira o
Ollama local (o Docker não repassa GPU AMD).

**Vários perfis do Claude Code.** Se você usa mais de uma conta, o card do
Claude Code lista cada perfil com um interruptor próprio. **Adicionar perfil**
escolhe a pasta de configuração e já liga o RAGX nela.

## 6. Usando com o agente (MCP)

Com o Claude Code conectado, o agente ganha ferramentas do RAGX. A ordem que
rende:

1. `get_dictionary`: orientação barata sobre o projeto.
2. `search_hybrid`: localizar onde algo está.
3. `build_context`: montar o contexto de trabalho dentro de um orçamento de
   tokens, com arquivo e linhas.
4. `get_chunk`: aprofundar num trecho.

Você não precisa chamar nada à mão: o RAGX entrega ao agente uma dica no início
da sessão dizendo para consultar o índice primeiro. Acompanhe o uso na tela
**Atividade**.

## 7. Usando pelo terminal

Abra um terminal **novo** (o PATH só vale na próxima sessão) e confira:

```powershell
ragx --version
```

Dentro de um projeto:

```powershell
ragx init                                # cria o ragx.toml
ragx security scan .                     # o que será bloqueado
ragx index .                             # indexa (incremental)
ragx search "como funciona a autenticação"
ragx context "implementar SSO" --tokens 3000    # contexto pronto, com fontes
ragx graph rebuild                       # grafo de entidades e relações
ragx dictionary generate                 # mapa barato do projeto
ragx watch                               # o índice acompanha suas edições
ragx doctor                              # o que está fora do lugar
ragx trial                               # estima (dois proxies, conservador) quanto token se economiza
```

Outros comandos úteis:

```powershell
ragx status                              # o índice está em dia? por quê?
ragx hooks install                       # hooks de git deste projeto
ragx claude status                       # o RAGX está ligado no Claude Code?
ragx claude off                          # desliga (e `on` religa)
ragx claude agent install                # opcional: o subagente `ragx-explorer` (explora sem encher o seu contexto)
ragx mcp serve                           # servidor MCP à mão
```

A referência completa dos comandos está em `docs/14-cli.md` no repositório.

## 8. Quando algo não funciona

| Sintoma | Causa provável | Saída |
|---|---|---|
| "RAGX CLI" não está verde | O bootstrap da instalação não terminou. | **Instalar / Tentar de novo** em *Conexões*. O log fica em `%APPDATA%\app\bootstrap.log`. |
| `ragx` não é reconhecido no terminal | O terminal foi aberto antes da instalação. | Abra um terminal novo. A CLI fica em `%USERPROFILE%\.local\bin`. |
| Cards em "Embeddings faltando" | Ollama parado ou sem o modelo. | Em *Conexões*: **Iniciar** e **Baixar nomic-embed-text**; depois **Gerar embeddings**. |
| Card preso em "Indexando…" | Um processo morreu no meio. | O painel descarta o estado se o processo dono não existe; **Atualizar agora** de novo. |
| O agente não usa o RAGX | O MCP não está registrado no perfil certo. | **Registrar para todos os projetos**, ou o interruptor do perfil. Reinicie o Claude Code. |
| Algo estranho no índice | Estado inconsistente. | `ragx doctor`; em último caso, **Reindexar do zero**. |

## 9. Desinstalar

Pelo Windows (**Configurações → Aplicativos**) ou pelo desinstalador na pasta de
instalação. Ele pergunta duas coisas:

1. **Remover também a CLI `ragx` e o registro no Claude Code?** (padrão: Sim)
2. **Remover também os dados do hub (`~\.ragx`)?** (padrão: Não)

Os índices dentro de cada projeto (`.ragx/`) e o Ollama **nunca** são tocados.
Desinstalar sem marcar a CLI deixa o `ragx` instalado.

## 10. O que esperar da beta

- **É uma beta.** A interface de linha de comando e o formato do índice ainda
  podem mudar entre versões.
- **A busca híbrida ainda não supera a busca por palavra-chave** no corpus de
  medição (recall@5 0,65 contra 0,77). O diagnóstico está em `docs/05-busca.md`.
  `ragx trial` mede, no **seu** projeto, se o contexto montado economiza token
  de verdade.
- O executável **não é assinado**; por isso o aviso do SmartScreen.
