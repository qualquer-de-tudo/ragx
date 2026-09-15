# Skills

Este arquivo descreve habilidades reutilizaveis do ecossistema de agentes.

---

## Habilidades disponiveis

| Habilidade | Arquivo | Uso principal |
|---|---|---|
| Questionamento estruturado | `ai/new-project.md` e `ai/import-project.md` | Coletar contexto antes de implementar |
| Leitura de contexto de modulo | `ai/module-context-reader.md` | Entender codigo existente antes de agir |
| Roteamento por intencao | `ai/triggers.md` | Acionar fluxo correto por contexto da mensagem |
| Referencias oficiais de bibliotecas | `ai/library-references.md` | Consultar links oficiais de docs para pacotes/libs/dependencias |
| Especialista em banco de dados (DBA) | `ai/dba.md` | Análise de schema, queries, índices, cache, busca e segurança de dados |
| Data Protection Officer (DPO) | `ai/dpo.md` | Conformidade com LGPD, GDPR e outras legislações; log de aceites e rejeições por módulo |

---

## Regra de uso de bibliotecas

Ao usar `ai/library-references.md`, lembrar:

1. A IA sugere, nao instala dependencias
2. O programador valida pacote e versao na fonte oficial
3. A IA so orienta implementacao apos confirmacao humana
