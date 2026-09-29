# RAGX-0120: A release publica o instalador do painel de ponta a ponta

| | |
|---|---|
| **Fase** | 17: Distribuição do painel em Windows, Linux e macOS |
| **Prioridade** | P1 |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0118 |
| **Documentação** | [release.yml](../../.github/workflows/release.yml) · [install/README.md](../../install/README.md) |
| **Status** | `todo` |

## Objetivo

O job `painel-windows` existe no `release.yml`, mas a última release (`v1.0.0-beta.3`,
17/09) saiu antes dele: nenhuma release publicada entregou o `.exe`. O fluxo com o
instalador anexado nunca rodou de ponta a ponta.

## Entregáveis

- [ ] Rodar o `release.yml` por `workflow_dispatch` com `draft: true` e conferir que o rascunho traz o `.exe`, o `.vsix`, o wheel, o sdist, os scripts e o `SHA256SUMS.txt`
- [ ] O `SHA256SUMS.txt` inclui o `RAGX-Painel-Setup-<versão>.exe`
- [ ] Notas da release citam o instalador do painel e o aviso do SmartScreen (executável não assinado)
- [ ] `install/README.md` e `src/app/README.md` dizem onde baixar o `.exe`
- [ ] Versão do painel alinhada à do produto (hoje o `package.json` do painel está em `0.0.0` e o instalador sai como `...-0.0.0.exe`)
- [ ] Se algo falhar no rascunho, corrigir o workflow e repetir até passar

## Fora de escopo

- Instaladores de Linux e macOS (RAGX-0122 e 0123)
- Assinatura de código (RAGX-0124)
- Publicar uma release de verdade (é decisão de versão, fora desta tarefa)

## Critérios de aceite

- [ ] Um rascunho de release, gerado pelo workflow, contém o instalador do painel e passa no smoke de instalar, verificar e desinstalar
- [ ] Baixar o `.exe` do rascunho e instalar numa máquina Windows limpa deixa "RAGX CLI" verde no painel
- [ ] O nome do instalador carrega a versão real do produto

## Testes

O smoke do job `painel-windows` (já existe); conferir a saída do rascunho à mão uma vez.

## Notas

O `package.json` do painel em `0.0.0` é o candidato mais provável a virar
armadilha: o `release.yml` já confere que a tag bate com o `pyproject`; falta a
mesma checagem (ou uma cópia da versão) para o painel.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Verificado num rascunho real de release
