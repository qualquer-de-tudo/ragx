/** "Em uso agora": houve chamada MCP, comando da CLI ou sessão do Claude no último minuto. */
export function LivePill() {
  return (
    <span className="live-pill">
      <span className="live-dot live-dot-on" aria-hidden="true" />
      em uso agora
    </span>
  )
}
