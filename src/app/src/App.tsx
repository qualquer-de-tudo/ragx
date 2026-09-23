import { useState } from 'react'
import { useSnapshot } from './hooks/useSnapshot'
import { ProjectList } from './components/ProjectList'
import { ProjectDetail } from './components/ProjectDetail'
import './App.css'

function App() {
  const { snapshot } = useSnapshot()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const projects = snapshot?.projects ?? []
  const selected = projects.find((p) => p.id === selectedId) ?? projects[0] ?? null

  return (
    <div className="app-shell">
      <ProjectList
        projects={projects}
        selectedId={selected?.id ?? null}
        onSelect={setSelectedId}
      />
      <ProjectDetail key={selected?.id} project={selected} />
    </div>
  )
}

export default App
