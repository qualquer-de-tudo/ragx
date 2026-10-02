import { HOW_KEEPS, HOW_LOCAL, HOW_STEPS } from '../components/onboarding/howItWorks'

/**
 * Tela "Como funciona" (fim da barra lateral): o caminho do dado em cinco passos, o que mantém o índice em dia sozinho
 * e onde ficam os dados. O passo 1 do onboarding usa o texto corrido de `HOW_IT_WORKS`.
 */
export function HowItWorksPage({
  onRestart,
  onOpenConnections,
}: {
  onRestart: () => void
  /** Leva para Conexões, onde se vê o estado dos hooks. Sem ele, o botão não aparece. */
  onOpenConnections?: () => void
}) {
  return (
    <section className="page how-page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Como funciona</h1>
          <p className="page-lede">Do seu código ao Claude Code, tudo dentro da sua máquina.</p>
        </div>
      </header>

      <section className="card how-flow" aria-labelledby="how-flow-title">
        <h2 className="card-title" id="how-flow-title">
          O caminho do dado
        </h2>
        <ol className="how-steps">
          {HOW_STEPS.map((s, i) => (
            <li key={s.title} className="how-step">
              <span className="how-step-n" aria-hidden="true">
                {i + 1}
              </span>
              <h3 className="how-step-title">{s.title}</h3>
              <p className="how-step-text">{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="how-cols">
        <section className="card how-keep" aria-labelledby="how-keep-title">
          <h2 className="card-title" id="how-keep-title">
            O que mantém o índice em dia
          </h2>
          <ul className="how-list">
            {HOW_KEEPS.map((k) => (
              <li key={k.title}>
                <p className="how-list-title">{k.title}</p>
                <p className="how-list-text">{k.text}</p>
              </li>
            ))}
          </ul>
          {onOpenConnections && (
            <button type="button" className="btn btn-sm how-link" onClick={onOpenConnections}>
              Ver os hooks em Conexões
            </button>
          )}
        </section>

        <section className="card how-local" aria-labelledby="how-local-title">
          <h2 className="card-title" id="how-local-title">
            Onde ficam seus dados
          </h2>
          <ul className="how-list how-list-plain">
            {HOW_LOCAL.map((t) => (
              <li key={t}>
                <p className="how-list-text">{t}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <div className="how-foot">
        <p className="dim">Quer rever a configuração inicial?</p>
        <button type="button" className="btn" onClick={onRestart}>
          Refazer configuração
        </button>
      </div>
    </section>
  )
}
