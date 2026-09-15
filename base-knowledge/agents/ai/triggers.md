# Triggers (Gatilhos de Acionamento)

Este arquivo define como o agente deve identificar, pelo contexto da mensagem do programador, qual fluxo iniciar:

1. Novo projeto
2. Importacao de projeto existente
3. Consulta de bibliotecas e documentacoes
4. Execucao de agente especifico

---

## Objetivo

Padronizar o roteamento inicial da conversa para reduzir ambiguidade e evitar execucao do fluxo errado.

---

## Ordem de prioridade dos gatilhos

Quando mais de um gatilho aparecer na mesma mensagem, usar esta prioridade:

1. Pedido explicito de agente especifico
2. Pedido de novo projeto
3. Pedido de importacao de projeto
4. Pedido de referencias de bibliotecas/documentacao
5. Fallback para leitura de contexto de modulo

---

## Gatilho 1 - Novo projeto

Acionar `ai/new-project.md` quando a mensagem indicar projeto do zero, por exemplo:

- "projeto novo"
- "iniciar do zero"
- "criar projeto"
- "onboarding inicial"
- "sem nada implementado"

Resposta esperada do agente:

1. Confirmar que vai iniciar `ai/new-project.md`
2. Conduzir os blocos obrigatorios do onboarding
3. Reforcar que seguranca e performance sao inegociaveis

---

## Gatilho 2 - Importacao de projeto

Acionar `ai/import-project.md` quando a mensagem indicar sistema em andamento, por exemplo:

- "importar projeto"
- "projeto existente"
- "repositorio legado"
- "sistema ja em producao"
- "mapear contexto atual"

Resposta esperada do agente:

1. Confirmar que vai iniciar `ai/import-project.md`
2. Conduzir entrevista de importacao completa
3. Consolidar contexto para os demais agentes

---

## Gatilho 3 - Agente especifico

Quando o programador pedir explicitamente um agente, executar o agente indicado.

Padroes aceitos na mensagem:

- "executar agente X"
- "usar agente X"
- "rodar agente X"
- "iniciar X"

Exemplos validos:

- "executar agente security-blue-team"
- "usar agente module-doc-generator"
- "rodar agente import-project"

Regra:

- Se o nome estiver claro e existir em `agents/ai/`, priorizar esse agente
- Se estiver ambiguo, perguntar qual agente deve ser usado antes de continuar

---

## Gatilho 4 - Banco de dados (DBA)
Acionar `ai/dba.md` quando a mensagem indicar qualquer tema relacionado a banco de dados, por exemplo:

- "criar tabela", "migration", "schema", "modelagem"
- "query lenta", "N+1", "gargalo de banco", "performance de banco"
- "indice", "index", "plano de execucao", "EXPLAIN"
- "Redis", "cache", "invalidacao de cache"
- "Elasticsearch", "Meilisearch", "busca", "indice de busca"
- "dado sensivel", "criptografar banco", "permissao de banco", "auditoria de dados"
- "qual banco usar", "escolher banco", "MongoDB vs PostgreSQL"
- "executar agente dba", "usar agente dba", "rodar agente dba"

Resposta esperada do agente:

1. Confirmar que vai iniciar `ai/dba.md`
2. Conduzir perguntas obrigatorias de contexto de dados
3. Analisar pelos tres pilares: performance, integridade, seguranca
4. Apresentar opcoes tecnicas e aguardar aprovacao antes de qualquer execucao

---

## Gatilho 5 - Protecao de dados e privacidade (DPO)

Acionar `ai/dpo.md` quando a mensagem indicar qualquer tema relacionado a dado pessoal, privacidade ou compliance, por exemplo:

- "dado pessoal", "PII", "informacao do usuario", "cadastro de usuario"
- "consentimento", "LGPD", "GDPR", "privacidade", "compliance"
- "dado de saude", "prontuario", "biometrico", "menor de idade"
- "transferencia de dados", "integracao com terceiro", "exportar dados"
- "log com dado pessoal", "auditoria de acesso"
- "base legal", "finalidade de coleta", "retencao de dados", "direito do titular"
- "executar agente dpo", "usar agente dpo", "rodar agente dpo"

Resposta esperada do agente:

1. Verificar se as legislacoes ja foram configuradas no projeto
2. Se nao: conduzir inicializacao obrigatoria de legislacoes antes de qualquer analise
3. Mapear dados pessoais envolvidos e analisar conformidade por legislacao ativa
4. Orientar o programador e aguardar posicionamento explicito (ACEITO / NAO ACEITO) para cada item
5. Registrar log completo da sessao no modulo afetado

---

## Gatilho 6 - Referencias de bibliotecas e documentacao

Acionar `ai/library-references.md` quando a mensagem indicar necessidade de links oficiais de libs/pacotes/dependencias, por exemplo:
- "quais docs oficiais para esse pacote"
- "me passe referencias de biblioteca para Node"
- "preciso da documentacao da dependencia X"
- "quais libs recomendadas com links oficiais"

Resposta esperada do agente:

1. Confirmar que vai iniciar `ai/library-references.md`
2. Fornecer links oficiais por stack e caso de uso
3. Reforcar validacao humana antes de qualquer instalacao

---

## Fallback (sem gatilho claro)

Se a mensagem nao deixar claro o fluxo inicial:

1. Fazer pergunta objetiva de desambiguacao:
   - "Voce quer iniciar um projeto novo, importar um projeto existente ou executar um agente especifico?"
2. Se o usuario nao responder claramente, usar `ai/module-context-reader.md` como fluxo padrao

---

## Regras de seguranca para qualquer gatilho

Independentemente do gatilho escolhido:

1. Nunca instalar dependencias automaticamente
2. Apenas sugerir pacote/lib, aguardar validacao humana e confirmacao do pacote final
3. Bloquear acoes destrutivas sem aprovacao explicita

---

## Referencias de uso rapido

- Prompt base e atalhos: `ai/prompts.md`
- Script de novo projeto: `ai/chat-script-new-project.md`
- Script de importacao: `ai/chat-script-import-project.md`

---

## Bloco de teste rapido (10 frases)

Use os exemplos abaixo para validar se o roteamento por contexto esta funcionando como esperado.

| Frase do programador | Roteamento esperado |
|---|---|
| "Quero iniciar um projeto novo do zero" | `ai/new-project.md` |
| "Vamos criar projeto sem nada implementado" | `ai/new-project.md` |
| "Preciso importar um repositorio legado" | `ai/import-project.md` |
| "Mapear contexto de um sistema ja em producao" | `ai/import-project.md` |
| "Executar agente security-blue-team" | agente especifico: `ai/security-blue-team.md` |
| "Usar agente module-doc-generator" | agente especifico: `ai/module-doc-generator.md` |
| "Quero iniciar onboarding inicial e depois rodar agente red-team" | agente especifico (prioridade 1): `ai/security-red-team.md` |
| "Temos projeto existente, mas quero executar agente import-project" | agente especifico (prioridade 1): `ai/import-project.md` |
| "Quais links oficiais para libs de validacao em Node?" | `ai/library-references.md` |
| "Preciso da documentacao do pacote para testes em PHP" | `ai/library-references.md` |
| "Preciso de ajuda com este modulo de agenda" | fallback: perguntar desambiguacao; se sem resposta, `ai/module-context-reader.md` |
| "Ajustar validacao de entrada no modulo de pacientes" | fallback: perguntar desambiguacao; se sem resposta, `ai/module-context-reader.md` |

### Criterio de aprovacao do teste rapido

1. O agente escolhe o fluxo esperado em 10/10 frases
2. Em frases ambiguas, o agente faz pergunta de desambiguacao antes de seguir
3. Quando houver pedido explicito de agente especifico junto com outro contexto, vale a prioridade do agente especifico
