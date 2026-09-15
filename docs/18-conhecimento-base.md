# 18 — Conhecimento base

> Regras que valem para TODOS os seus projetos, baixadas uma vez por máquina.
> Ver [ADR-0013](adr/ADR-0013-conhecimento-base-compartilhado.md).

## O problema

Guardrails do agente, padrões de arquitetura, política de revisão: esse
conhecimento não pertence a repositório nenhum. Sem ferramenta, ele é copiado
para dentro de cada projeto — e três meses depois cada cópia diz uma coisa
diferente.

## O desenho

```
  ~/.ragx/base/agents/           ← uma cópia, por MÁQUINA
           │
           ├── indexado em projeto-a  como  @base/agents/...
           ├── indexado em projeto-b  como  @base/agents/...
           └── indexado em projeto-c  como  @base/agents/...

  knowledge/base.json            ← a RECEITA viaja no Git (algumas centenas de bytes)
```

Quatro propriedades sustentam isso:

1. **Mesmo gate.** Conteúdo de terceiro entra por `iter_files`, com um
   `SecurityGate` enraizado na própria fonte. Repositório de regras com um
   `.env` esquecido não contamina o seu índice.
2. **Prefixo visível.** `@base/` aparece em todo resultado. O agente sabe que
   é referência externa, não descrição deste projeto.
3. **Conteúdo não versionado.** `knowledge/` guarda origem, ref e commit. Não
   os arquivos.
4. **Opt-in por projeto.** Instalar na máquina não indexa nada: o projeto
   precisa declarar em `ragx.toml`.

## Uso

### Instalar

```bash
ragx base add https://github.com/renan-s-oliveira/agents
```

Clona em `~/.ragx/base/agents/`, declara em `ragx.toml` e indexa. Também
aceita caminho local (útil enquanto você edita as regras):

```bash
ragx base add ./base-knowledge/agents --name agents
```

### Ver o que está instalado

```bash
ragx base list
```

```
Conhecimento base   C:\Users\voce\.ragx\base

fonte    arquivos  commit    origem
agents         36  a3f91c2e  https://github.com/renan-s-oliveira/agents
```

### Reproduzir em outra máquina

Quem clona o repositório roda:

```bash
ragx base sync
```

Lê `ragx.toml` e `knowledge/base.json`, instala o que falta — no commit
registrado — e indexa.

### Atualizar

```bash
ragx base update            # todas as fontes
ragx base update agents     # uma
```

Só reindexa se o commit mudou.

### Desligar sem apagar

```bash
ragx base disable agents && ragx index .
```

Os documentos `@base/agents/*` saem do índice no próximo `index`. Nada de
limpeza manual: o pipeline trata fonte ausente como arquivo removido.

## Configuração

```toml
[base]
enabled = true
sources = ["https://github.com/renan-s-oliveira/agents"]
# Orçamento próprio, menor que o do projeto: regra é texto curto.
max_file_bytes = 262144
```

**`sources` é o que decide o que é indexado.** Uma fonte instalada mas não
declarada fica em disco e fora do índice — de propósito
([ADR-0013](adr/ADR-0013-conhecimento-base-compartilhado.md), regra 4).

## Como isso aparece para o agente

```
2  0.031  @base/agents/engineering/validations.md:70-92 › Validations > O que validar
       **R-VAL-09 — Identificador de outra entidade é validado como existente
       E acessível.** `invoice_id` que existe mas pertence a outro cliente é
       IDOR, a falha de autorização mais comum em API.
```

O playbook do MCP (`get_playbook`) instrui explicitamente: `@base/` é
referência; quando divergir do código do projeto, **o projeto ganha**.

## Orçamento

Conhecimento base não conta no orçamento de Git, porque não vai para o Git. O
que vai é `base.json` — no projeto RAGX, 132 bytes.

Conta, sim, no banco local (`.ragx/knowledge.db`) e no tempo de indexação: 36
documentos e ~230 chunks para o repositório `agents`.

## Ver também

- [17 — Multiprojeto e federação](17-multiprojeto-e-federacao.md) — contratos
  entre serviços, que é outro problema
- [ADR-0009](adr/ADR-0009-tres-camadas-de-conhecimento.md) — as três camadas
- [ADR-0008](adr/ADR-0008-security-gate-antes-do-parser.md) — por que o gate
  vem antes
