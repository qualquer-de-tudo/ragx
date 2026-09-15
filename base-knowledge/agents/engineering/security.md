# Security

Este arquivo define as regras de seguranca obrigatorias para qualquer implementacao. Seguranca e inegociavel.

---

## Principios

1. Seguranca e requisito de entrada, nao etapa final
2. Nenhuma entrega e considerada pronta com vulnerabilidade critica aberta
3. Qualquer excecao deve ser aprovada por humano responsavel e registrada em debito tecnico

---

## Regra obrigatoria sobre pacotes e dependencias

O agente **nunca pode instalar pacotes, dependencias, libs ou plugins** automaticamente.

Fluxo obrigatorio:

1. O agente apenas sugere opcoes de pacote/dependencia com justificativa tecnica
2. O programador valida no site/repositorio oficial do projeto da dependencia
3. O programador decide se aprova a sugestao ou escolhe alternativa
4. A instalacao e feita manualmente pelo programador, da forma correta para o projeto
5. O programador informa ao agente qual pacote foi instalado (ou qual alternativa foi escolhida)
6. O agente usa essa informacao para ler a documentacao correta e orientar uso seguro

Sem essa confirmacao humana, o agente nao deve assumir que a dependencia foi aceita.

---

## Regras minimas de seguranca por implementacao

1. Validar e sanitizar toda entrada externa
2. Aplicar autenticacao e autorizacao nos pontos de acesso
3. Nunca expor secrets, tokens ou dados sensiveis em logs
4. Usar consultas parametrizadas para evitar injecao
5. Tratar erros sem vazar detalhes internos
6. Aplicar principio do menor privilegio para acessos

---

## Integracao com agentes de seguranca

- `ai/security-blue-team.md`: analise defensiva e recomendacoes de correcao
- `ai/security-red-team.md`: simulacao ofensiva para identificar vetores de ataque

Se vulnerabilidade for identificada e nao puder ser corrigida na mesma tarefa:

1. Registrar em `quality/tech-debt.md` com tipo `security`
2. Definir prioridade (CRITICA/ALTA/MEDIA/BAIXA)
3. Registrar mitigacao temporaria
4. Bloquear aprovacao se risco for CRITICA

---

## Criterio de bloqueio

Aprovacao deve ser bloqueada quando houver:

- Vulnerabilidade critica sem mitigacao valida
- Falha de autenticacao/autorizacao em fluxo sensivel
- Dependencia adicionada sem validacao humana explicita
