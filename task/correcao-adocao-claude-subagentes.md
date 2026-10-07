# Correção de adoção do RAGX no Claude Code com subagentes

## Problema observado

No `crm-project`, 354 arquivos de transcript do perfil fullstackclub continham zero chamadas MCP ao RAGX, apesar do registro e dos hooks instalados. O MCP respondeu ao diagnóstico direto. O hook só orientava SessionStart; o lembrete era compartilhado por toda a sessão, inclusive filhos. O painel contava `nudge` como consulta, produzindo 1 de 5 sessões mesmo sem chamada.

## Escopo

- Orientar filhos via SubagentStart, com saída JSON própria, sem criar sessões fictícias.
- Orientar novamente ao retomar e usar o cwd do evento.
- Separar dedupe do lembrete por agente.
- Corrigir a adoção: lembrete não é consulta.
- Testar migração idempotente, preservação de hooks e contagem.

## Fora de escopo

- Forçar chamadas do modelo ou bloquear Grep, Read e Bash.
- Interceptar comandos shell para inferir edições.
- Alterar permissões do Claude ou instruções de negócio do CRM.
- Corrigir concorrência de index.pending no Windows nesta tarefa.
- Publicar release ou reconstruir o instalador desktop.

## Verificação

Suíte Python rápida, segurança, lint e `npm run check` do painel. Diagnóstico MCP usa processo próprio, sem atribuí-lo ao Claude.

## Resultado

- 2.133 testes Python passaram, 6 ignorados; segurança: 158 passaram.
- Painel: 2.014 testes passaram; lint e tipagem passaram. Ruff e mypy passaram.
- CLI da máquina instalada em modo editável; `claude heal --profile fullstackclub` acrescentou a dica de subagente, com backup.
- MCP do executável instalado respondeu e listou as seis ferramentas. Hook SubagentStart retornou JSON válido para CRM mesmo executado de outra pasta.
- CRM reindexado: 958 documentos, 17.677 chunks e embeddings, estado fresh no momento da verificação.
- Ainda depende de retomar a sessão do Claude para validar adoção real; as chamadas de diagnóstico não são atribuídas ao Claude. O painel instalado requer nova build para exibir a correção da contagem.
