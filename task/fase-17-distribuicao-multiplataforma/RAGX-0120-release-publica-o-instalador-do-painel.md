# RAGX-0120: A release publica o instalador do painel de ponta a ponta

| | |
|---|---|
| **Fase** | 17: Distribuição do painel em Windows, Linux e macOS |
| **Prioridade** | P1 |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0118 |
| **Documentação** | [release.yml](../../.github/workflows/release.yml) · [install/README.md](../../install/README.md) |
| **Status** | `review` |

## Objetivo

O job `painel-windows` existe no `release.yml`, mas a última release (`v1.0.0-beta.3`,
17/09) saiu antes dele: nenhuma release publicada entregou o `.exe`. O fluxo com o
instalador anexado nunca rodou de ponta a ponta.

## Entregáveis

- [x] Rodar o `release.yml` por `workflow_dispatch` com `draft: true` e conferir que o rascunho traz o `.exe`, o `.vsix`, o wheel, o sdist, os scripts e o `SHA256SUMS.txt`
- [x] O `SHA256SUMS.txt` inclui o `RAGX-Painel-Setup-<versão>.exe`
- [x] Notas da release citam o instalador do painel e o aviso do SmartScreen (executável não assinado)
- [x] `install/README.md` e `src/app/README.md` dizem onde baixar o `.exe`
- [x] Versão do painel alinhada à do produto (hoje o `package.json` do painel está em `0.0.0` e o instalador sai como `...-0.0.0.exe`)
- [x] Se algo falhar no rascunho, corrigir o workflow e repetir até passar

## Fora de escopo

- Instaladores de Linux e macOS (RAGX-0122 e 0123)
- Assinatura de código (RAGX-0124)
- Publicar uma release de verdade (é decisão de versão, fora desta tarefa)

## Critérios de aceite

- [x] Um rascunho de release, gerado pelo workflow, contém o instalador do painel e passa no smoke de instalar, verificar e desinstalar
- [ ] Baixar o `.exe` do rascunho e instalar numa máquina Windows limpa deixa "RAGX CLI" verde no painel
- [x] O nome do instalador carrega a versão real do produto

## Testes

O smoke do job `painel-windows` (já existe); conferir a saída do rascunho à mão uma vez.

## Notas

O `package.json` do painel em `0.0.0` é o candidato mais provável a virar
armadilha: o `release.yml` já confere que a tag bate com o `pyproject`; falta a
mesma checagem (ou uma cópia da versão) para o painel.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Verificado num rascunho real de release

## Andamento (2026-09-29)

Feito no código: o painel acompanha a versão do produto (`1.0.0-beta.3`); a
release confere tag x `pyproject.toml` x painel x extensão; o disparo manual
não usa mais o nome do ramo como tag; as notas saem da seção da versão no
CHANGELOG e explicam o `.exe` e o SmartScreen; `scripts/versao.py` sobe a
versão, fecha o CHANGELOG e cria a tag. O passo de montar as notas e a checagem
de versão foram simulados localmente.

Feito em 2026-09-29, direto numa release de verdade (`v1.0.0-beta.4`, publicada
por decisão da pessoa): a página traz o `.exe`, o `.vsix`, o wheel, o sdist, os
scripts e o `SHA256SUMS.txt`, e o smoke do painel instalou, viu
`ragx 1.0.0-beta.4` responder e desinstalou.

O que o fluxo de ponta a ponta revelou, e foi corrigido no workflow:

- o `setup-uv` define `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, e o uv do instalador
  herdava isso: o `ragx.exe` ia para `D:\a\_temp\uv-tool-bin-dir` e o smoke o
  procurava em `~\.local\bin`. Os passos de instalar, verificar e desinstalar
  agora rodam sem essas variáveis;
- o stub do NSIS morre às vezes com `0xC0000005` nos primeiros 2-3 s, antes de
  extrair arquivos (2 de 5 instalações na mesma imagem `windows-2025`, com o
  mesmo `.exe`). O smoke tenta de novo só nesse código, até 3 vezes, e loga o
  módulo que crashou (evento 1000). **Causa ainda não identificada**: se o
  aviso aparecer numa release com o módulo, vale uma tarefa própria.

Falta só o critério 2, manual: instalar o `.exe` da release numa máquina
Windows limpa e ver "RAGX CLI" verde no painel.
