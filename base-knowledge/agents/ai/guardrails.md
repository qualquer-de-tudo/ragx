# Guardrails

Este arquivo define os bloqueios obrigatorios do agente. Se um item abaixo for acionado, o agente deve parar e solicitar acao humana.

---

## Bloqueios obrigatorios

1. Nao executar acoes destrutivas sem aprovacao explicita
2. Nao alterar contratos de API sem aprovacao explicita
3. Nao executar migracoes de banco sem aprovacao explicita
4. Nao operar em producao sem aprovacao explicita
5. Nao instalar pacotes, dependencias, libs ou plugins automaticamente

---

## Regra de dependencias

Para dependencias externas, o agente deve:

1. Sugerir opcoes tecnicas com justificativa
2. Pedir para o programador validar na fonte oficial
3. Aguardar confirmacao do pacote escolhido
4. Somente depois orientar uso com base na documentacao do pacote confirmado

O agente nao pode executar comandos de instalacao sem autorizacao e validacao humana.
