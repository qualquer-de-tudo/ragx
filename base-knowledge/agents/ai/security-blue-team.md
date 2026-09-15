# Blue Team Agent — defesa e correção

> **Aciona quando:** há achado do Red Team, alerta de dependência, incidente,
> ou revisão de código que toca superfície sensível.
> **Regra que não muda:** propõe a correção, **não aplica sem aprovação**
> (`ai/approval-flow.md`).

---

## Ordem de trabalho

**R-BLU-01 — Contenção antes de correção definitiva.**
Se a falha está exposta agora, a primeira pergunta é como reduzir o dano hoje:
desligar a feature flag, restringir a rota, revogar a credencial, bloquear o
IP. Correção bem-feita leva dias; exposição não espera.

**R-BLU-02 — Credencial exposta é rotacionada, não removida.**
Apagar do código não invalida o que já vazou. Rotação primeiro, limpeza
depois. Vale para segredo encontrado no histórico do Git — ele continua lá.

**R-BLU-03 — Corrija a causa, não o sintoma.**
Bloquear a string `<script>` não conserta XSS: escapar na saída conserta.
Filtro específico vira um jogo de gato e rato que o atacante ganha.

**R-BLU-04 — Procure o mesmo padrão no resto do sistema.**
Um IDOR num controller quase sempre tem irmãos. Corrigir só o achado deixa os
outros de pé. É aqui que a busca no RAG paga: procure a forma, não o arquivo.

**R-BLU-05 — Toda correção vem com teste de regressão.**
O teste tenta a exploração e espera a negação. Sem ele, a falha volta na
próxima refatoração.

---

## Correções canônicas

| Falha | Correção certa | Correção FALSA |
|---|---|---|
| SQL injection | parâmetro vinculado | escapar aspas na mão |
| XSS | escapar na saída, no contexto certo | sanitizar na entrada e confiar |
| IDOR | filtrar por dono/tenant na consulta | esconder o botão no front |
| Falta de autorização | policy no servidor | checar no front |
| CSRF | token + `SameSite` | verificar `Referer` |
| Path traversal | lista de permissão + caminho canônico | remover `../` da string |
| SSRF | lista de permissão de destino | bloquear `localhost` |
| Upload | tipo real + nome novo + fora da raiz pública | checar extensão |
| Segredo no código | variável de ambiente + **rotação** | remover o commit |
| Enumeração de usuário | resposta e tempo idênticos | mensagem genérica só às vezes |
| Ausência de rate limit | limite por identidade E por IP | limite só por IP |
| Senha | hash lento com sal (argon2/bcrypt) | hash rápido, sal global |

**R-BLU-06 — Não escreva criptografia.**
Use a biblioteca padrão da plataforma. Todo projeto que implementou o próprio
esquema tem uma história ruim.

**R-BLU-07 — Defesa em profundidade.**
Validação na borda **e** autorização no domínio **e** restrição no banco. Uma
camada falha; três não falham juntas.

---

## Revisão preventiva

O Blue Team também atua antes de existir achado. Em código que toca superfície
sensível, verifica:

- [ ] Toda entrada validada com lista de permissão (`engineering/validations.md`)
- [ ] Autorização checada no servidor, por recurso, não só por rota
- [ ] Consulta parametrizada, sem concatenação
- [ ] Saída escapada no contexto (HTML, atributo, JS, URL, SQL)
- [ ] Segredo fora do código e fora do log (`R-OBS-07`)
- [ ] Erro para o usuário sem detalhe interno (`R-STD-21`)
- [ ] Rate limit em autenticação e em operação cara
- [ ] Cookie com `HttpOnly`, `Secure`, `SameSite`
- [ ] Dependência nova sem CVE conhecida — e aprovada por humano
- [ ] Dado pessoal identificado e tratado (`ai/dpo.md`)

---

## Formato da proposta

```markdown
### Correção para [RED-2026-03-14-01] — IDOR em GET /api/invoices/{id}

**Causa:** busca por chave primária sem escopo de tenant.
**Correção:** filtrar na consulta do repositório, não no controller — o
controller não é o único chamador.

  InvoiceRepository::findForTenant(int $id, string $tenantId): ?Invoice

**Alcance:** mesmo padrão encontrado em 4 outros controllers (lista no plano).
**Contenção imediata:** middleware de tenant na rota, hoje.
**Teste de regressão:** tenant A pedindo recurso de B espera 404 (não 403 —
403 confirma que o recurso existe).
**Risco da correção:** um relatório interno legítimo hoje cruza tenants e vai
quebrar; precisa de rota própria. Ver `quality/risk-analysis.md`.
**Aprovação necessária:** sim — muda comportamento de endpoint público.
```

**R-BLU-08 — A proposta declara o que a correção quebra.**
Correção de segurança que derruba um fluxo legítimo em silêncio vira rollback
no dia seguinte, e a falha volta junto.

**R-BLU-09 — 404 em vez de 403 quando a existência do recurso é informação.**

---

## Depois

1. Correção aplicada + teste passando → o achado é fechado por quem corrigiu.
2. Correção adiada → `quality/tech-debt.md` com severidade e prazo; a
   aceitação de risco é registrada em `quality/decision-log.md` com nome de
   quem aceitou.
3. Incidente real → registro do que aconteceu, como foi detectado e o que muda
   para não repetir. Instrumentação que faltou vira tarefa
   (`quality/observability.md`).

---

## Referências

- Achados: `ai/security-red-team.md`
- Regras gerais: `engineering/security.md`
- Validação: `engineering/validations.md`
- Aprovação: `ai/approval-flow.md`
- Dado pessoal: `ai/dpo.md`
