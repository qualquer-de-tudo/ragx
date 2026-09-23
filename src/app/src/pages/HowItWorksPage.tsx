import { HOW_IT_WORKS, HOW_IT_WORKS_TITLE } from '../components/onboarding/howItWorks'

/** Tela "Como funciona": o mesmo texto do passo 1 do onboarding. */
export function HowItWorksPage({ onRestart }: { onRestart: () => void }) {
  return (
    <section className="page">
      <header className="page-head">
        <h1 className="page-title">Como funciona</h1>
      </header>
      <div className="card prose how-card">
        <h2 className="card-title">{HOW_IT_WORKS_TITLE}</h2>
        {HOW_IT_WORKS.map((p) => (
          <p key={p}>{p}</p>
        ))}
        <button type="button" className="btn" onClick={onRestart}>
          Refazer configuração
        </button>
      </div>
    </section>
  )
}
