import http from 'node:http'

/**
 * GET que devolve o JSON do corpo, ou `null` para qualquer falha (status
 * diferente de 200, tempo esgotado, erro de rede, JSON inválido). Nunca lança.
 */
export function httpGetJson(url: string, timeoutMs: number): Promise<unknown | null> {
  return new Promise((resolve) => {
    try {
      const req = http.get(url, { timeout: timeoutMs }, (res) => {
        if (res.statusCode !== 200) {
          res.resume()
          resolve(null)
          return
        }
        res.setEncoding('utf-8')
        let body = ''
        res.on('data', (chunk: string) => {
          body += chunk
        })
        res.on('end', () => {
          try {
            resolve(JSON.parse(body) as unknown)
          } catch {
            resolve(null)
          }
        })
        res.on('error', () => resolve(null))
      })
      req.on('timeout', () => {
        req.destroy()
        resolve(null)
      })
      req.on('error', () => resolve(null))
    } catch {
      resolve(null)
    }
  })
}
