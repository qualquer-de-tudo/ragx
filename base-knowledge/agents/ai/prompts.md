# Prompts

Este arquivo centraliza prompts padrao para uso do time no chat com o agente.

---

## Prompt base (uso geral)

Use este prompt para iniciar qualquer tarefa de implementacao:

```text
Siga o fluxo de agent-behavior.

Antes de executar qualquer alteracao:
1. Verifique se o projeto ja foi importado (ou se e projeto novo)
2. Gere/valide contexto do modulo
3. Monte plano em DRAFT e aguarde aprovacao

Regras obrigatorias:
- Seguranca e performance inegociaveis
- Nao instalar dependencias automaticamente
- Nao executar acoes destrutivas sem aprovacao explicita
```

---

## Atalhos de onboarding (novo/importacao)

Para padronizar o uso pelo time, utilize os scripts prontos abaixo:

- Novo projeto: `ai/chat-script-new-project.md`
- Importacao de projeto existente: `ai/chat-script-import-project.md`
- Referencias de bibliotecas: `ai/chat-script-library-references.md`

Fluxo recomendado:

1. Copiar o texto do script correspondente
2. Colar como primeira mensagem no chat
3. Responder aos blocos de perguntas
4. Confirmar o resumo final antes de salvar mudancas de contexto
