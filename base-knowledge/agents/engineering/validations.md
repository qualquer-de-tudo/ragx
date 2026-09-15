# Validations — validação obrigatória de entrada

> **Quando carregar:** ao criar ou alterar qualquer ponto de entrada —
> endpoint, comando, consumidor de fila, webhook, importador de arquivo.

Premissa única: **toda entrada é hostil até ser validada.** Não importa se vem
do front que você mesmo escreveu, de um parceiro com contrato assinado ou de
um job interno.

---

## Onde validar

**R-VAL-01 — Valide na BORDA, garanta no DOMÍNIO.**
A borda (FormRequest, DTO de entrada, schema) rejeita formato inválido cedo e
com mensagem útil. O domínio protege a invariante — porque nem toda chamada
passa pela borda.

**R-VAL-02 — Todo ponto de entrada tem validação. Sem exceção.**

| Entrada | Onde valida |
|---|---|
| HTTP | FormRequest / schema de request |
| CLI | assinatura do comando + checagem de argumento |
| Fila / job | valida o payload ao desserializar |
| Webhook | assinatura HMAC **e** schema do corpo |
| Upload | tipo real, tamanho, nome sanitizado |
| Importação de arquivo | linha a linha, com relatório de rejeição |
| Variável de ambiente | na subida da aplicação, não no primeiro uso |

**R-VAL-03 — Validação de formato não é autorização.**
Que o campo `account_id` seja um UUID válido não diz que este usuário pode
acessar aquela conta. São duas checagens, em dois lugares
(`engineering/security.md`).

---

## O que validar

**R-VAL-04 — Lista de permissão, não lista de proibição.**
Declare o que é aceito. Tentar enumerar o que é perigoso sempre deixa um caso
de fora.

**R-VAL-05 — Todo campo declara tipo, obrigatoriedade e limite.**
String sem tamanho máximo é vetor de exaustão de memória e de estouro de
coluna. Número sem faixa aceita negativo onde não deveria.

**R-VAL-06 — Campo não declarado é rejeitado, não ignorado.**
Ignorar em silêncio esconde erro de integração por semanas. Se a política do
projeto é ignorar, que seja decisão registrada, não acidente.

**R-VAL-07 — Nunca vincule a entrada direto ao model.**
Mass assignment com o corpo cru deixa o cliente escrever `is_admin`. Passe por
DTO ou por lista explícita de campos.

**R-VAL-08 — Valide a relação entre campos, não só cada um.**
`data_fim >= data_inicio`, `desconto <= total`, "se `tipo = PJ`, `cnpj` é
obrigatório". É onde a maioria dos bugs de regra mora.

**R-VAL-09 — Identificador de outra entidade é validado como existente E
acessível.**
`invoice_id` que existe mas pertence a outro cliente é IDOR, a falha de
autorização mais comum em API.

**R-VAL-10 — Normalize depois de validar, não antes.**
`trim`, caixa, formato de documento e de telefone acontecem sobre um valor já
aceito. Normalizar antes mascara entrada malformada.

---

## Casos que exigem cuidado extra

**R-VAL-11 — Upload: confie no conteúdo, não na extensão.**
Verifique o tipo real (magic bytes), imponha tamanho máximo, gere nome novo,
guarde fora da raiz pública. `foto.jpg.php` é o clássico.

**R-VAL-12 — Valor monetário não é ponto flutuante.**
Inteiro em centavos ou decimal exato. `0.1 + 0.2` já custou dinheiro a muita
gente.

**R-VAL-13 — Data e hora: aceite ISO-8601, armazene em UTC, apresente no fuso
do usuário.**

**R-VAL-14 — Paginação tem teto.**
`per_page` sem limite é negação de serviço com um parâmetro. Teto e default
explícitos.

**R-VAL-15 — Ordenação e filtro vêm de lista fechada.**
`?sort=` concatenado em SQL é injection. Mapeie o valor recebido para uma
coluna conhecida.

**R-VAL-16 — Webhook: valide a assinatura ANTES de ler o corpo.**
E rejeite timestamp antigo, senão o replay funciona.

---

## Como responder

**R-VAL-17 — Erro de validação é 422 (ou o equivalente da stack), com o campo
nomeado.**
Uma resposta genérica obriga quem integra a adivinhar.

**R-VAL-18 — Devolva TODOS os erros, não o primeiro.**
Quem integra corrige de uma vez, em vez de descobrir um por requisição.

**R-VAL-19 — A mensagem não repete a entrada crua.**
Ecoar o valor recebido dentro da resposta ou do log é como XSS refletido e
vazamento de dado nascem. Diga qual campo e qual regra, não o que veio.

**R-VAL-20 — Falha de validação é evento de log, sem o dado sensível.**
Registre campo e regra violada. Nunca o valor de senha, token, CPF ou cartão
(`ai/dpo.md`).

---

## O que o agente faz

1. Ao criar endpoint, cria a validação **no mesmo commit**. Endpoint sem
   validação não é entrega parcial: é vulnerabilidade.
2. Ao alterar um contrato, atualiza a validação e o teste de contrato juntos.
3. Ao encontrar entrada sem validação fora do escopo da tarefa, registra em
   `quality/tech-debt.md` com prioridade alta — não conserta de passagem.

---

## Referências

- Segurança e autorização: `engineering/security.md`
- Dados pessoais: `ai/dpo.md`
- Testes de borda: `engineering/testing.md`
- Anti-patterns relacionados: `core/patterns.md` (`A-PAT-09`)
