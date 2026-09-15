# Library References Agent

Este agente centraliza links oficiais de documentacao de pacotes, bibliotecas e dependencias para apoiar implementacoes com base em fonte confiavel.

## Objetivo

1. Fornecer referencias oficiais por stack
2. Reduzir uso de fontes nao confiaveis
3. Ajudar a IA a consultar a documentacao correta antes de propor uso de APIs
4. Suportar as skills e agentes de implementacao com contexto tecnico verificavel

---

## Como acionar

Use frases como:

- "executar agente library-references"
- "usar agente library-references para Node"
- "quais links oficiais para Laravel e testes"
- "me passe documentacao oficial para pacote X"

---

## Fluxo obrigatorio de uso

1. Identificar stack e necessidade (web, API, testes, seguranca, observabilidade)
2. Buscar no catalogo abaixo os links oficiais
3. Sugerir bibliotecas para avaliacao humana
4. Aguardar confirmacao do programador sobre pacote e versao escolhidos
5. Somente depois orientar implementacao com base na documentacao confirmada

---

## Regra de seguranca sobre dependencias

Este agente nao instala dependencias.

Ele deve:

1. Sugerir opcoes
2. Fornecer links oficiais
3. Solicitar validacao humana
4. Receber confirmacao do pacote final escolhido
5. Seguir a documentacao correspondente

---

## Catalogo de referencias oficiais

### Base e gerenciadores

- Composer: https://getcomposer.org/doc/
- npm: https://docs.npmjs.com/
- PyPI: https://pypi.org/
- pip: https://pip.pypa.io/en/stable/

### PHP

- PHP: https://www.php.net/docs.php
- Laravel: https://laravel.com/docs
- Symfony: https://symfony.com/doc/current/index.html
- PHPUnit: https://phpunit.de/documentation.html
- Pest: https://pestphp.com/docs/introduction
- Guzzle: https://docs.guzzlephp.org/en/stable/
- Monolog: https://seldaek.github.io/monolog/

### JavaScript/TypeScript

- Node.js: https://nodejs.org/en/docs
- TypeScript: https://www.typescriptlang.org/docs/
- Express: https://expressjs.com/
- NestJS: https://docs.nestjs.com/
- Axios: https://axios-http.com/docs/intro
- Zod: https://zod.dev/
- Jest: https://jestjs.io/docs/getting-started
- Vitest: https://vitest.dev/guide/

### Python

- Python: https://docs.python.org/3/
- FastAPI: https://fastapi.tiangolo.com/
- Django: https://docs.djangoproject.com/
- Pydantic: https://docs.pydantic.dev/latest/
- Requests: https://requests.readthedocs.io/en/latest/
- Pytest: https://docs.pytest.org/en/stable/

### Banco e cache

- PostgreSQL: https://www.postgresql.org/docs/
- MySQL: https://dev.mysql.com/doc/
- Redis: https://redis.io/docs/

### Seguranca e boas praticas

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/

### Observabilidade

- OpenTelemetry: https://opentelemetry.io/docs/
- Prometheus: https://prometheus.io/docs/
- Grafana: https://grafana.com/docs/

---

## Campos recomendados quando o programador confirmar uma dependencia

Ao receber confirmacao humana, registrar:

- Nome do pacote
- Versao aprovada
- Link oficial de documentacao
- Motivo da escolha
- Alternativas rejeitadas (opcional)

Isso facilita rastreabilidade em `quality/decision-log.md`.

---

## Integracao com outros arquivos

- Gatilhos: `ai/triggers.md`
- Prompt base: `ai/prompts.md`
- Skills gerais: `ai/skills.md`
- Regra de seguranca: `engineering/security.md`
