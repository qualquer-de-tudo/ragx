# Política de Segurança

O RAGX indexa código de repositórios de terceiros e é desenhado com o
princípio de que **nenhum segredo entra na base de conhecimento** — ver
[docs/02-seguranca.md](docs/02-seguranca.md) para o modelo de ameaça completo
(`SecurityGate`, `SecurityScanner`, política `strict`/`balanced`).

Se você encontrou uma forma de um segredo escapar do Security Gate — indexado
como chunk, embarcado num embedding, exposto por uma ferramenta MCP, ou
vazado no `.rag` exportado — isso é uma vulnerabilidade, não um bug comum.

## Como reportar

**Não abra uma issue pública.** Use o
[Report a vulnerability](https://github.com/qualquer-de-tudo/ragx/security/advisories/new)
do GitHub (aba Security deste repositório) para reportar em privado.

Inclua, se possível:
- o caminho ou padrão de arquivo que deveria ter sido bloqueado/redigido e não foi;
- a saída de `ragx security scan .` sobre o caso (sem colar o segredo real —
  se for uma chave de verdade, revogue-a antes de mais nada);
- versão do RAGX (`ragx --version`) e política de segurança configurada
  (`[security] policy` em `ragx.toml`).

## Escopo

Dentro do escopo: qualquer caminho por onde um segredo do projeto indexado
alcance disco, log, embedding, grafo, resposta MCP ou pacote `.rag` sem passar
pelo gate. As nove ameaças modeladas (A1–A9) estão em
[docs/02-seguranca.md](docs/02-seguranca.md#modelo-de-ameaça).

Fora do escopo (documentado como tal): usuário local malicioso com acesso de
escrita à máquina onde o RAGX roda — ver "Fora do escopo do MVP" no mesmo
documento.

## Versões suportadas

O projeto está em beta (`1.0.0-beta.1`). Correções de segurança vão para a
versão mais recente publicada; não há suporte a versões anteriores.
