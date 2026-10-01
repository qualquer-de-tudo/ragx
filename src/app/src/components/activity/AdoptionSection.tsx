import type { AdoptionSummary } from '../../types/ragx-bridge'
import { formatNumber, formatPercent } from '../../format'
import { Section } from '../shell/Card'

function since(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** "3 de 38 sessões chamaram o RAGX (8%)": a razão em texto, com o período REAL e a lista por projeto. */
function adoptionLine(a: AdoptionSummary): string {
  return `${formatNumber(a.withCalls)} de ${formatNumber(a.sessions)} sessões chamaram o RAGX (${formatPercent(a.withCalls / a.sessions)})`
}

/**
 * Adoção pelos agentes (RAGX-0190, S13): das sessões abertas em projeto indexado, quantas chamaram o RAGX. A janela é
 * a dos logs lidos (até 14 dias): a tela diz "desde dd/mm", não "14 dias", quando o log é mais curto.
 */
export function AdoptionSection({ adoption: a }: { adoption: AdoptionSummary }) {
  return (
    <Section title="Adoção pelos agentes">
      {a.sessions === 0 ? (
        <p className="dim">Nenhuma sessão registrada ainda.</p>
      ) : (
        <>
          <p className="adoption-line" role="status">
            {adoptionLine(a)}
            {a.since ? ` · desde ${since(a.since)}` : ''}
          </p>
          <ul className="adoption-projects" aria-label="Adoção por projeto">
            {a.byProject.map((p) => (
              <li key={p.projectId}>
                {p.projectName}: {formatNumber(p.withCalls)} de {formatNumber(p.sessions)}
              </li>
            ))}
          </ul>
        </>
      )}
      {(a.unidentified > 0 || a.callsWithoutStart > 0) && (
        <p className="hint">
          Fora da razão:{' '}
          {[
            a.unidentified > 0 ? `${formatNumber(a.unidentified)} evento(s) sem identificação de sessão` : null,
            a.callsWithoutStart > 0 ? `${formatNumber(a.callsWithoutStart)} sessão(ões) com chamadas e sem início registrado` : null,
          ]
            .filter(Boolean)
            .join('; ')}
          .
        </p>
      )}
    </Section>
  )
}
