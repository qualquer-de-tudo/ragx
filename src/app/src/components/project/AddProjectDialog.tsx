import { AddProjectFlow } from './AddProjectFlow'
import { Modal } from '../ui/Modal'

/**
 * Diálogo "Adicionar projeto". O corpo é o `AddProjectFlow`; ao enfileirar,
 * fecha e deixa a fila no topo mostrar o andamento. Fechado, não monta nada,
 * então cada abertura começa do zero.
 */
export function AddProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null
  return (
    <Modal title="Adicionar projeto" onClose={onClose}>
      <AddProjectFlow onDone={onClose} onCancel={onClose} />
    </Modal>
  )
}
