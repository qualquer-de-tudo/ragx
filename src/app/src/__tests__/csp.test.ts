import { describe, expect, it } from 'vitest'
import { CSP, CSP_DIRECTIVES, cspPlugin } from '../../csp'

function directive(name: string): string[] {
  return (CSP_DIRECTIVES[name] ?? '').split(/\s+/).filter(Boolean)
}

describe('CSP de produção', () => {
  it('nega tudo por padrão e só abre o que o painel usa', () => {
    expect(directive('default-src')).toEqual(["'none'"])
    expect(directive('script-src')).toEqual(["'self'"])
    expect(directive('style-src')).toEqual(["'self'"])
    expect(directive('base-uri')).toEqual(["'none'"])
    expect(directive('form-action')).toEqual(["'none'"])
  })

  it("sem 'unsafe-eval', e 'unsafe-inline' só no atributo style", () => {
    expect(CSP).not.toContain('unsafe-eval')
    for (const name of Object.keys(CSP_DIRECTIVES)) {
      if (name !== 'style-src-attr') expect(directive(name), name).not.toContain("'unsafe-inline'")
    }
    expect(directive('style-src-attr')).toEqual(["'unsafe-inline'"])
  })

  it('nenhum host http, https ou curinga', () => {
    expect(CSP).not.toMatch(/https?:|\*|wss?:/)
  })

  it('o plugin injeta o <meta> só no build, antes de qualquer script', () => {
    const plugin = cspPlugin()
    expect(plugin.apply).toBe('build')
    const hook = plugin.transformIndexHtml as { order: string; handler: () => Array<{ tag: string; attrs: Record<string, string>; injectTo: string }> }
    const [tag] = hook.handler()
    expect(tag.tag).toBe('meta')
    expect(tag.attrs['http-equiv']).toBe('Content-Security-Policy')
    expect(tag.attrs.content).toBe(CSP)
    expect(tag.injectTo).toBe('head-prepend')
  })
})
