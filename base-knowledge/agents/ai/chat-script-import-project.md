# Chat Script - Import Existing Project

Use this message as-is in chat:

```text
Quero importar um projeto ja em andamento para a estrutura de contexto.

Execute o fluxo ai/import-project.md e faca todas as perguntas obrigatorias para consolidar o contexto do projeto.

Objetivo:
1. Mapear arquitetura, stack e modulos
2. Mapear riscos tecnicos e de negocio
3. Definir regras de seguranca e performance (inegociaveis)
4. Definir caminhos de artefatos (.plan.md, .review.md, .decision.md, .techdebt.md)
5. Atualizar os arquivos de contexto para os demais agentes

No fim, quero:
1. Resumo de importacao para validacao
2. Lista do que foi atualizado
3. Lista de lacunas pendentes
4. Registro de decisao do onboarding de importacao

Importante sobre dependencias:
Voce nao pode instalar pacotes/dependencias automaticamente.
Apenas sugira. Eu vou validar na fonte oficial, instalar manualmente e te avisar o pacote final para voce seguir com a documentacao correta.
```