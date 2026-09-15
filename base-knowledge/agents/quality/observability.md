# Observability — logs, métricas e rastreabilidade

> **Quando carregar:** ao criar endpoint, job, integração externa ou qualquer
> caminho que possa falhar em produção.

Critério para saber se está bom: **dá para diagnosticar um incidente sem
reproduzir o erro e sem acesso ao banco de produção?** Se não dá, falta
instrumentação.

---

## Logs

**R-OBS-01 — Log estruturado, não frase.**
Campos nomeados em JSON, não `"erro ao processar fatura 123 do cliente 45"`.
Frase não é filtrável nem agregável.

```json
{"level":"error","event":"invoice.issue_failed","invoice_id":"inv_123",
 "tenant_id":"t_45","reason":"gateway_timeout","duration_ms":3021,
 "trace_id":"9f2c…"}
```

**R-OBS-02 — Todo log carrega correlação.**
`trace_id` (ou `request_id`) propagado por request, job e chamada externa. Sem
isso não se reconstrói o que aconteceu.

**R-OBS-03 — Nível tem significado combinado.**

| Nível | Significa | Acorda alguém? |
|---|---|---|
| `debug` | detalhe de desenvolvimento | não (desligado em prod) |
| `info` | fato de negócio relevante | não |
| `warning` | degradou, seguiu funcionando | não, mas é revisado |
| `error` | operação falhou, usuário afetado | sim, se recorrente |
| `critical` | serviço comprometido | sim, imediatamente |

**R-OBS-04 — `error` é acionável.**
Se ninguém vai fazer nada a respeito, é `warning`. Log de erro que todo mundo
aprendeu a ignorar torna o próximo erro real invisível.

**R-OBS-05 — Exceção engolida deixa rastro.**
`catch` que decide seguir registra por quê. É a diferença entre "tratamos esse
caso" e "sumiu" (`R-STD-20`).

**R-OBS-06 — Erro loga a causa, não só a mensagem.**
Exceção original encadeada, com stack. `"Erro ao salvar"` sem causa custa horas.

---

## O que NUNCA vai para o log

**R-OBS-07 — Zero credencial.**
Senha, token, chave de API, cookie de sessão, header `Authorization`.

**R-OBS-08 — Zero dado pessoal sensível.**
CPF, cartão, endereço, dado de saúde. Use identificador interno; quem tem
permissão resolve para a pessoa (`ai/dpo.md`).

**R-OBS-09 — Zero corpo de request completo "por garantia".**
Registre os campos que importam para o diagnóstico. O corpo inteiro é onde
segredo vaza sem ninguém perceber.

**R-OBS-10 — Mascare o que precisa aparecer.**
`****1234`, `a***@dominio.com`. Máscara no ponto de escrita, nunca confiando
num filtro depois.

---

## Métricas

**R-OBS-11 — Quatro sinais, sempre: taxa, erro, latência, saturação.**
Por endpoint e por job.

**R-OBS-12 — Latência é percentil, nunca média.**
p50, p95, p99. Média esconde exatamente a cauda que dói.

**R-OBS-13 — Métrica de negócio ao lado da técnica.**
Faturas emitidas, pagamentos recusados, filas paradas. É o que mostra que o
sistema "está de pé e não está funcionando".

**R-OBS-14 — Cardinalidade controlada.**
`user_id` como label de métrica explode o armazenamento. Identificador vai no
log; métrica tem dimensão limitada.

**R-OBS-15 — Fila tem métrica de tamanho, idade e taxa de falha.**
Job que falha em silêncio é o incidente que ninguém vê chegando.

---

## Rastreamento

**R-OBS-16 — Chamada externa é span com duração e resultado.**
Quando o parceiro degrada, você precisa provar que foi ele.

**R-OBS-17 — O `trace_id` chega ao usuário em caso de erro.**
"Código de referência: 9f2c…" transforma um chamado de suporte vago em uma
busca de um segundo.

---

## Saúde

**R-OBS-18 — `/health` responde raso; `/ready` verifica dependências.**
Confundir os dois derruba o serviço inteiro quando um dependente oscila.

**R-OBS-19 — Alerta é sobre sintoma do usuário, não sobre causa interna.**
"Taxa de erro do checkout acima de 2%" acorda alguém. "CPU em 80%" não —
talvez esteja apenas trabalhando.

---

## O que o agente faz

1. Instrumenta **no mesmo commit** do código novo. Observabilidade adicionada
   depois só se lembra do que já se sabe que quebra.
2. Antes de escrever qualquer log, verifica `R-OBS-07` a `R-OBS-10`. Vazamento
   por log é o mais comum e o mais duradouro — o log fica em backup por anos.
3. Ao mexer em caminho crítico sem instrumentação, registra em
   `quality/tech-debt.md`.
4. Ao investigar incidente, começa perguntando o que os dados mostram, não o
   que o código parece fazer.

---

## Referências

- Dados pessoais: `ai/dpo.md`
- Segurança: `engineering/security.md`
- Performance e limites: `engineering/performance.md`
- Análise de risco: `quality/risk-analysis.md`
