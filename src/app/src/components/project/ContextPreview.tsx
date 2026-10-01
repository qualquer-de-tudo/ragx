import { useId, useState } from 'react'
import type { ContextPreview as Preview } from '../../types/ragx-bridge'
import { ipcErrorMessage } from '../../ipcError'
import { formatNumber } from '../../format'
import { Section } from '../shell/Card'
import { SkeletonRegion, SkeletonText } from '../ui/Skeleton'

type View = { phase: 'idle' } | { phase: 'loading' } | { phase: 'ok'; preview: Preview } | { phase: 'error'; message: string }

const MAX_LENGTH = 500

/**
 * Preview do `build_context` (RAGX-0187): o que o agente receberia para uma pergunta, sem mostrar código. A pergunta
 * vive SÓ em `useState`: nada de `localStorage`, nada de cache em disco; some ao trocar de projeto (`key` na página) e
 * ao desmontar. Roda por Enter ou pelo botão, nunca a cada tecla.
 */
export function ContextPreview({ projectId }: { projectId: string }) {
  const inputId = useId()
  const [question, setQuestion] = useState('')
  const [view, setView] = useState<View>({ phase: 'idle' })

  const run = async (e: { preventDefault: () => void }) => {
    e.preventDefault()
    if (question.trim() === '' || view.phase === 'loading') return
    setView({ phase: 'loading' })
    try {
      setView({ phase: 'ok', preview: await window.ragx.previewContext(projectId, question) })
    } catch (err) {
      // só o motivo do processo principal, que nunca repete a pergunta
      setView({ phase: 'error', message: ipcErrorMessage(err) })
    }
  }

  return (
    <Section title="Pré-visualizar o contexto">
      <form className="preview-form" onSubmit={(e) => void run(e)}>
        <label htmlFor={inputId} className="hint">
          Escreva uma pergunta ou tarefa e veja quais trechos o agente receberia. A pergunta não é gravada em lugar nenhum.
        </label>
        <div className="preview-row">
          <input
            id={inputId}
            type="text"
            className="search-input"
            value={question}
            maxLength={MAX_LENGTH}
            autoComplete="off"
            spellCheck={false}
            placeholder="Ex.: como o pedido é criado?"
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button type="submit" className="btn btn-primary" disabled={question.trim() === '' || view.phase === 'loading'}>
            Pré-visualizar
          </button>
          <button
            type="button"
            className="btn btn-quiet"
            onClick={() => {
              setQuestion('')
              setView({ phase: 'idle' })
            }}
          >
            Limpar
          </button>
        </div>
      </form>

      {view.phase === 'loading' && (
        <SkeletonRegion label="Montando o contexto. A primeira busca pode levar alguns segundos.">
          <SkeletonText lines={3} />
          <p className="hint">Montando o contexto. A primeira busca pode levar alguns segundos.</p>
        </SkeletonRegion>
      )}

      {view.phase === 'error' && <p className="callout callout-error">Não foi possível montar o contexto: {view.message}</p>}

      {view.phase === 'ok' &&
        (view.preview.fragments.length === 0 ? (
          <p className="dim" role="status">
            Nenhum trecho do índice responde a essa pergunta.
          </p>
        ) : (
          <div className="preview-result">
            <p className="preview-summary" role="status">
              {view.preview.fragments.length} trecho(s) · {formatNumber(view.preview.estimatedTokens)} de{' '}
              {formatNumber(view.preview.budget)} tokens{view.preview.intent ? ` · intenção ${view.preview.intent}` : ''}
            </p>
            <ol className="preview-list" aria-label="Trechos que o agente receberia">
              {view.preview.fragments.map((f, i) => (
                <li key={`${f.documentPath}:${f.lines[0]}:${i}`} className="preview-item">
                  <span className="mono preview-path">
                    {f.documentPath}:{f.lines[0]}-{f.lines[1]}
                  </span>
                  <span className="dim">
                    {f.symbol ?? f.headingPath ?? 'sem símbolo'} · {formatNumber(f.tokens)} tokens
                    {f.reason ? ` · ${f.reason}` : ''}
                    {f.compressed ? ' · comprimido' : ''}
                  </span>
                </li>
              ))}
            </ol>
            {view.preview.dropped.length > 0 && (
              <p className="hint">
                Ficaram de fora:{' '}
                {view.preview.dropped.map((d) => `${formatNumber(d.count)} por ${d.why}`).join(', ')}.
              </p>
            )}
          </div>
        ))}
    </Section>
  )
}
