# Política de segurança

O RAGX existe para que um agente trabalhe num repositório real **sem que
segredo nenhum entre na base de conhecimento**. Uma falha que quebre essa
promessa não é um bug comum: o dado vazado já foi para o índice, e daí para o
log e para o provedor do modelo. Leve isso em conta ao reportar.

## Como reportar

**Não abra issue pública** para vulnerabilidade. Uma issue aberta é um aviso
para quem quiser explorar antes da correção existir.

> **Canal ainda não definido.** Este repositório ainda não tem um endereço de
> segurança publicado nem o GitHub Security Advisories habilitado. Enquanto
> isso não acontece, o caminho é abrir um **rascunho de advisory privado** em
> *Security → Advisories → New draft security advisory*, ou contatar quem
> mantém o repositório em particular.
>
> Este bloco é um marcador explícito, não um canal real: ele fica aqui até
> alguém com permissão no repositório publicar um endereço de verdade. Se você
> mantém este projeto, substitua-o.

## O que incluir

Quanto mais completo o relato, menor o tempo até a correção:

- **versão** do RAGX (`ragx --version`) e da extensão do VS Code;
- **sistema operacional** e versão do Python;
- **o que acontece** e **o que deveria acontecer**;
- **passo a passo mínimo para reproduzir** — de preferência partindo de
  `ragx init` num projeto novo;
- **impacto**: que dado sai, para onde, e o que o atacante precisa controlar
  (arquivo no repositório? configuração? um servidor MCP?);
- qualquer *proof of concept* — como arquivo anexo, não colado num canal
  público.

Se o relato envolve um segredo de verdade (chave, token, credencial),
**não o inclua**. Descreva o formato e substitua o valor. Um relato de
vazamento não precisa vazar de novo.

## O que interessa especialmente

Áreas em que uma falha é séria por construção:

- **Security Gate** — qualquer caminho que faça conteúdo bloqueado chegar ao
  índice, ao `knowledge/`, a um resultado de busca, ao `build_context` ou a uma
  ferramenta MCP.
- **Fronteira do MCP** — o servidor não pode ler filesystem, abrir rede nem
  executar processo. Um caminho de código que consiga isso é uma falha, mesmo
  que precise de configuração incomum.
- **Travessia de caminho** — `..`, caminho absoluto, symlink ou junção que
  faça o RAGX indexar ou servir algo fora da raiz do projeto.
- **Injeção de comando** — em qualquer ponto que monte linha de comando:
  instalador, extensão do VS Code, `ragx base` (que clona repositórios).
- **Workspace malicioso** — um repositório feito para atacar quem o indexa:
  `ragx.toml` manipulado, `.ragignore` que desliga proteção, nomes de arquivo
  hostis.
- **Servidor MCP falso** — a extensão do VS Code sobe o executável indicado em
  `ragx.command`; um caminho que faça isso escapar do que a pessoa configurou
  é relevante.

## O que **não** é vulnerabilidade

Para poupar seu tempo:

- **Falso positivo do scanner** (arquivo legítimo bloqueado). É bug de
  usabilidade — abra issue normal. `ragx security scan .` mostra o motivo.
- **Segredo que o RAGX bloqueia corretamente** aparecer em `ragx security
  scan`: é o comando fazendo o trabalho dele, na sua máquina.
- **O agente conseguir ler um arquivo pelas ferramentas do próprio agente**
  (o `Read` do Claude Code, por exemplo). O RAGX protege o que entra no
  ÍNDICE; ele não controla as outras ferramentas do cliente.
- **`allow_write = true` deixar o agente reindexar.** É o desenho, documentado
  em [ADR-0012](docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md). O agente
  manda no índice; não manda na máquina.

## Enquanto a correção não sai

Pedimos que você:

- **dê tempo** antes de divulgar — o combinado usual é 90 dias, ou menos se a
  correção sair antes;
- **não publique** *exploit* funcional, detalhe de exploração nem o relato
  completo antes de a versão corrigida estar disponível;
- **não acesse dado que não seja seu** para demonstrar a falha, e não a teste
  em repositório de terceiros;
- fale conosco se achar que o prazo está longo demais — prazo se negocia, e a
  gravidade pesa nisso.

Da nossa parte: confirmamos o recebimento, dizemos se aceitamos o relato e o
que achamos da gravidade, avisamos quando a correção sair, e creditamos quem
reportou nas notas da versão — a menos que você prefira não ser citado.

## Versões que recebem correção

O RAGX está em **beta** (`1.0.0-beta.x`). Só a última versão publicada recebe
correção; não há backport para betas anteriores. O formato do índice e a
interface de linha de comando ainda podem mudar entre betas.

## Como o RAGX se defende hoje

Para contextualizar um relato — o detalhe está em
[docs/02-seguranca.md](docs/02-seguranca.md):

- o **Security Gate roda antes do parser**: o que ele bloqueia nunca é lido,
  então não existe no banco e nenhuma consulta o alcança
  ([ADR-0008](docs/adr/ADR-0008-security-gate-antes-do-parser.md));
- **duas fases** — nome do arquivo antes de abrir, conteúdo depois;
- o **MCP é casca fina**, sem `os`, `subprocess`, `pathlib` nem cliente HTTP,
  verificado por teste arquitetural em `tests/security/test_architecture.py`;
- a suíte de segurança é **bloqueante** e roda isolada no CI, com oito
  superfícies de vazamento verificadas;
- o CI **quebra** se um `.env` com credencial entrar no índice do projeto de
  teste.
