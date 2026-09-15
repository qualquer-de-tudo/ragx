# ADR-0013 — Conhecimento base compartilhado entre projetos

- **Status:** aceito
- **Data:** 2026-09-15
- **Contexto:** Fase 11
- **Relacionado:** [ADR-0009](ADR-0009-tres-camadas-de-conhecimento.md), [ADR-0010](ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md), [ADR-0008](ADR-0008-security-gate-antes-do-parser.md)

## Contexto

Existe conhecimento que não pertence a repositório nenhum: regras de
arquitetura, guardrails do agente, convenções de código, política de revisão.
Vale para todos os projetos da pessoa, e hoje ou é colado em cada repositório
(e diverge) ou vive só na cabeça de alguém.

O caso concreto: o repositório `renan-s-oliveira/agents`, que define como o
agente de IA deve se comportar. Ele precisa estar disponível em toda sessão, em
qualquer projeto.

## Decisão

Uma **quarta origem** de conhecimento, ortogonal às três camadas do ADR-0009:

```
~/.ragx/base/<fonte>/     conteúdo baixado, uma vez por MÁQUINA
        ↓ indexado como
@base/<fonte>/...         dentro do índice de CADA projeto que declara a fonte
```

Quatro regras sustentam o desenho.

### 1. Conteúdo de terceiro passa pelo mesmo gate

A base entra pelo `iter_files`, com um `SecurityGate` enraizado na própria
fonte. Um repositório de regras com um `.env` esquecido não contamina o índice
de quem o instalou. Teste arquitetural garante que `ragx.base` nunca chama
`read_bytes` nem `open` — ele clona, registra e conta; quem lê bytes é o
walker.

### 2. O prefixo `@base/` é obrigatório e visível

Nunca colide com caminho de arquivo do projeto (`@` não é início de caminho
válido) e aparece em todo resultado de busca. O agente sabe, sem perguntar, que
aquilo é referência externa e não descrição deste projeto — e o playbook diz
que, na divergência, o projeto ganha.

### 3. O conteúdo NÃO é versionado; o registro é

`knowledge/` guarda a receita (`base.json`: origem, ref, commit), não os
arquivos. Dois motivos:

- Base não é reidratável. O ADR-0010 dispensa versionar conteúdo porque ele
  está no working tree — e `@base/...` não está.
- Duplicar o mesmo conjunto de regras em N repositórios queima o orçamento de
  Git em N cópias idênticas.

Quem clona roda `ragx base sync` e reconstrói a mesma base, no mesmo commit.

### 4. Instalar não basta — o projeto precisa DECLARAR

`~/.ragx/base/` é global. Se a instalação bastasse, um `ragx base add` feito
num projeto mudaria em silêncio o índice de todos os outros da máquina.

A declaração vive em `ragx.toml`, `[base] sources`. `ragx base add` a escreve
por padrão, preservando os comentários do arquivo.

> Esta regra foi escrita **depois** de a suíte quebrar: sete testes de
> pipeline passaram a indexar 40 documentos onde esperavam 4, porque a fonte
> instalada nesta máquina vazou para todo projeto temporário. O sintoma
> apareceu em teste; em produção apareceria como a busca devolvendo a regra de
> outro contexto, sem explicação.

## Consequências

**Positivas**

- Uma cópia por máquina, N projetos usando.
- A base viaja no Git como receita de poucas centenas de bytes.
- `ragx base update` atualiza todos os projetos de uma vez.
- Fonte desabilitada ou removida some do índice no próximo `index`, sozinha.

**Negativas aceitas**

- Mais uma coisa para manter atualizada. Mitigado por `ragx base update`, que
  aceita todas as fontes de uma vez e só reindexa o que mudou de commit.
- Conteúdo de terceiro no índice aumenta o ruído da busca. Mitigado pelo
  prefixo visível e pelo orçamento próprio (`base.max_file_bytes`, menor que o
  do projeto).
- Fonte local (`kind: path`) não viaja no manifesto: o caminho não existiria na
  máquina do colega. Só fonte Git é reproduzível — e é isso que o manifesto
  registra.

## Alternativas descartadas

**Copiar as regras para dentro de cada repositório.** É o que se faz hoje sem
ferramenta, e é justamente o que produz divergência silenciosa entre projetos.

**Um projeto no hub de federação.** O hub resolve contratos entre serviços
(quem provê, quem consome). Regra de arquitetura não é contrato de API; usar o
mesmo mecanismo confundiria as duas coisas na busca e no dicionário.

**Submódulo Git.** Traz o conteúdo para dentro do repositório (orçamento), exige
que todo clone saiba de submódulo, e continua sendo uma cópia por projeto.
