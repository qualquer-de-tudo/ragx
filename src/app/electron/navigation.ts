export const DEV_SERVER_URL = 'http://localhost:5173'
const DEV_SERVER_ORIGIN = new URL(DEV_SERVER_URL).origin

/**
 * Em dev, a janela só pode navegar dentro do servidor do Vite. Compara a
 * origem de verdade: um prefixo de texto aceitaria
 * `http://localhost:5173.outro-site.com` ou `http://localhost:51730`.
 */
export function isDevServerUrl(url: string): boolean {
  try {
    return new URL(url).origin === DEV_SERVER_ORIGIN
  } catch {
    return false
  }
}
