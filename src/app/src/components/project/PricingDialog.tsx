import { useState } from 'react'
import type { Pricing } from '../../types/ragx-bridge'
import { CURRENCY_LABEL, MAX_PRICE, parsePriceInput, type Currency } from '../../money'
import { Modal } from '../ui/Modal'
import { Segmented } from '../ui/Segmented'

/**
 * "Configurar preço" (RAGX-0186): moeda e preço por 1 milhão de tokens de ENTRADA. O RAGX não embute tabela de preços
 * nem câmbio: o número é da pessoa. "Remover preço" volta ao estado sem valor em dinheiro.
 */
export function PricingDialog({
  current,
  onSave,
  onClose,
}: {
  current: Pricing | null
  onSave: (pricing: Pricing | null) => Promise<boolean>
  onClose: () => void
}) {
  const [currency, setCurrency] = useState<Currency>(current?.currency ?? 'BRL')
  const [text, setText] = useState(current ? String(current.perMTokInput).replace('.', ',') : '')
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: { preventDefault: () => void }) => {
    e.preventDefault()
    const price = parsePriceInput(text)
    if (price === null) {
      setError(`Informe um número maior que 0 e até ${MAX_PRICE.toLocaleString('pt-BR')}.`)
      return
    }
    if (await onSave({ currency, perMTokInput: price })) onClose()
  }

  return (
    <Modal title="Configurar preço" onClose={onClose}>
      <form className="pricing-form" onSubmit={(e) => void submit(e)}>
        <p className="hint">
          O RAGX não sabe quanto você paga: informe o preço de ENTRADA por 1 milhão de tokens do modelo que você usa. Nada
          é buscado na internet.
        </p>
        <Segmented
          label="Moeda"
          value={currency}
          options={(Object.keys(CURRENCY_LABEL) as Currency[]).map((c) => ({ value: c, label: CURRENCY_LABEL[c] }))}
          onChange={setCurrency}
        />
        <label className="pricing-field">
          <span>Preço por 1 milhão de tokens de entrada</span>
          <input
            type="text"
            inputMode="decimal"
            className="search-input"
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setError(null)
            }}
            aria-invalid={error !== null}
            aria-describedby={error ? 'pricing-error' : undefined}
            autoComplete="off"
            spellCheck={false}
            data-autofocus
          />
        </label>
        {error && (
          <p className="callout callout-error" id="pricing-error" role="alert">
            {error}
          </p>
        )}
        <div className="pricing-actions">
          {current && (
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => {
                void onSave(null).then((ok) => ok && onClose())
              }}
            >
              Remover preço
            </button>
          )}
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary">
            Salvar
          </button>
        </div>
      </form>
    </Modal>
  )
}
