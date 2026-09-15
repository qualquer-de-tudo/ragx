# Regras de segurança

Derivado do ruleset do RAGX. **Este arquivo é obrigatório**: um perfil sem ele
não compila.

## Nunca

- Nunca peça, leia ou reproduza conteúdo de `.env`, `credentials*`, `*.pem`,
  `id_rsa`, `*.key` ou qualquer arquivo bloqueado pelo gate.
- Nunca escreva um segredo em código, log, teste, comentário ou mensagem de commit.
- Nunca desabilite regra de segurança para "fazer passar".
- Nunca envie conteúdo do projeto para serviço externo sem autorização explícita.

## Sempre

- Credencial vem de variável de ambiente, jamais de arquivo versionado.
- Ao encontrar um segredo comitado, PARE e avise — não tente corrigir sozinho.
- Use `rag security scan .` antes de propor um commit.

## Por quê

O índice do RAGX não contém segredos por construção: o gate roda antes do
parser. Se você acha que precisa de um segredo para completar a tarefa, a
resposta correta é pedir ao humano, não procurar no repositório.
