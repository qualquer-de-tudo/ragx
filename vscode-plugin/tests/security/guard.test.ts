/**
 * A garantia que mais importa: a UI nunca mostra o que o RAGX bloqueou (§43).
 *
 * O plugin não tem uma segunda implementação de segurança — o gate do RAGX
 * decide, e o que ele bloqueia nunca entra no índice. Estes testes cobrem a
 * camada seguinte: se algo marcado como bloqueado chegar mesmo assim, ele não
 * chega à tela.
 */

import { describe, expect, it } from 'vitest';

import { dropBlocked, isBlocked, safeRelPath, safeText } from '../../src/security/guard';

describe('isBlocked', () => {
  it.each([
    'ACCESS_DENIED',
    'resposta: ACCESS_DENIED para o caminho',
    'SECURITY_BLOCKED',
    'valor = [REDACTED:aws-key]',
    'senha = [REDIGIDO]',
  ])('reconhece marcação em %s', (texto) => {
    expect(isBlocked(texto)).toBe(true);
  });

  it.each([
    { blocked: true },
    { access: 'denied' },
    { code: 'ACCESS_DENIED' },
    { code: 'security_blocked' },
  ])('reconhece objeto bloqueado %j', (obj) => {
    expect(isBlocked(obj)).toBe(true);
  });

  it('não bloqueia conteúdo legítimo', () => {
    expect(isBlocked('class AuthService { login() {} }')).toBe(false);
    expect(isBlocked({ code: 'not_found' })).toBe(false);
    expect(isBlocked(null)).toBe(false);
    expect(isBlocked(42)).toBe(false);
  });
});

describe('dropBlocked', () => {
  it('remove os bloqueados e CONTA quantos', () => {
    const { kept, removed } = dropBlocked([
      { content: 'ok 1' },
      { content: 'ACCESS_DENIED' },
      { content: 'ok 2' },
      { blocked: true },
    ]);
    expect(kept).toHaveLength(2);
    expect(removed).toBe(2);
  });

  it('a contagem existe para a UI poder DIZER que omitiu algo', () => {
    // Uma lista que encolhe em silêncio faz a pessoa concluir que o
    // conhecimento não existe — pior que dizer que foi filtrado.
    const { removed } = dropBlocked([{ code: 'ACCESS_DENIED' }]);
    expect(removed).toBeGreaterThan(0);
  });
});

describe('safeRelPath', () => {
  it.each(['/etc/passwd', 'C:/Windows/System32', '../../.env', 'a/../../b', '', null])(
    'recusa %j',
    (ruim) => {
      expect(safeRelPath(ruim)).toBeUndefined();
    },
  );

  it.each(['src/auth.py', 'docs/arquitetura.md', 'a.py', '@base/agents/ai/guardrails.md'])(
    'aceita %s',
    (bom) => {
      expect(safeRelPath(bom)).toBe(bom);
    },
  );

  it('normaliza separador do Windows', () => {
    expect(safeRelPath('src\\ragx\\auth.py')).toBe('src/ragx/auth.py');
  });
});

describe('safeText', () => {
  it('remove caracteres de controle que quebram o layout', () => {
    expect(safeText('antes\u0000\u0007depois')).toBe('antesdepois');
  });

  it('preserva quebra de linha e tabulação, que são conteúdo', () => {
    expect(safeText('linha 1\nlinha 2\tfim')).toBe('linha 1\nlinha 2\tfim');
  });

  it('corta texto gigante em vez de travar a renderização', () => {
    const enorme = 'a'.repeat(20_000);
    const saida = safeText(enorme, 100);
    expect(saida.length).toBeLessThan(200);
    expect(saida.endsWith('…')).toBe(true);
  });

  it('devolve string vazia para não-string', () => {
    expect(safeText(undefined)).toBe('');
    expect(safeText({ a: 1 })).toBe('');
  });
});
