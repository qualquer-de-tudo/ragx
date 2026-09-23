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

/**
 * POST com corpo JSON. Devolve o status e o JSON da resposta (`json: null` se o
 * corpo não for JSON), ou `null` para falha de transporte (rede, tempo
 * esgotado). Nunca lança.
 */
export function httpPostJson(
  url: string,
  body: unknown,
  timeoutMs: number,
): Promise<{ status: number; json: unknown | null } | null> {
  return new Promise((resolve) => {
    try {
      const payload = JSON.stringify(body)
      const req = http.request(
        url,
        {
          method: 'POST',
          timeout: timeoutMs,
          headers: { 'content-type': 'application/json', 'content-length': Buffer.byteLength(payload) },
        },
        (res) => {
          res.setEncoding('utf-8')
          let text = ''
          res.on('data', (chunk: string) => {
            text += chunk
          })
          res.on('end', () => {
            let json: unknown | null
            try {
              json = JSON.parse(text) as unknown
            } catch {
              json = null
            }
            resolve({ status: res.statusCode ?? 0, json })
          })
          res.on('error', () => resolve(null))
        },
      )
      req.on('timeout', () => {
        req.destroy()
        resolve(null)
      })
      req.on('error', () => resolve(null))
      req.end(payload)
    } catch {
      resolve(null)
    }
  })
}
