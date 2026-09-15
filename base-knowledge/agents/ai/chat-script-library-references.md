# Chat Script - Library References

Use this message as-is in chat:

```text
Quero executar o agente de referencias de bibliotecas.

Execute o fluxo ai/library-references.md para me passar links oficiais de documentacao de pacotes, libs e dependencias para este contexto:

Contexto tecnico:
- Stack principal: {preencher}
- Caso de uso: {preencher}
- Area: {API | testes | seguranca | observabilidade | banco | validacao}

Objetivo:
1. Sugerir opcoes de bibliotecas confiaveis
2. Trazer somente links oficiais da documentacao
3. Explicar quando usar cada opcao de forma curta

Regra obrigatoria:
Voce nao pode instalar pacotes/dependencias automaticamente.
Apenas sugira. Eu vou validar na fonte oficial, instalar manualmente e te informar qual pacote e versao foram aprovados.

No fim, quero:
1. Lista de bibliotecas sugeridas
2. Link oficial de cada uma
3. Recomendacao principal com justificativa curta
4. Proximo passo apos eu confirmar o pacote escolhido
```