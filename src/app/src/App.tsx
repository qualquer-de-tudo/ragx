import { useState } from 'react'
import { useSnapshot } from './hooks/useSnapshot'
import { ProjectList } from './components/ProjectList'
import { ProjectDetail } from './components/ProjectDetail'
import './App.css'

const byName = (a: { name: string }, b: { name: string }) =>
  a.name.localeCompare(b.name, 'pt-BR', { sensitivity: 'base' })

function App() {
  const { snapshot } = useSnapshot()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const projects = [...(snapshot?.projects ?? [])].sort(byName)
  const selected = projects.find((p) => p.id === selectedId) ?? projects[0] ?? null

  return (
    <div className="app-shell">
      <ProjectList
        projects={projects}
        selectedId={selected?.id ?? null}
        onSelect={setSelectedId}
        loading={snapshot === null}
        updatedAt={snapshot?.generatedAt ?? null}
      />
      <ProjectDetail key={selected?.id} project={selected} />
    </div>
  )
}

export default App
