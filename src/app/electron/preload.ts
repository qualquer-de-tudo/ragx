import { contextBridge, ipcRenderer } from 'electron'
import type {
  ActivityEvent,
  AdoptionSummary,
  ClaudeIntegration,
  ConnectionCheck,
  ContextPreview,
  DiscoverResult,
  JobRequest,
  JobView,
  OllamaBenchmark,
  PanelSettings,
  Pricing,
  RagxBridge,
  SecurityScanResult,
  Snapshot,
  TrialResult,
} from '../src/types/ragx-bridge'

const ragx: RagxBridge = {
  getSnapshot: (): Promise<Snapshot> => ipcRenderer.invoke('ragx:getSnapshot'),
  onSnapshot: (cb: (snapshot: Snapshot) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, snapshot: Snapshot) => cb(snapshot)
    ipcRenderer.on('ragx:snapshot', listener)
    return () => ipcRenderer.removeListener('ragx:snapshot', listener)
  },
  getActivity: (): Promise<ActivityEvent[]> => ipcRenderer.invoke('ragx:getActivity'),
  getAdoption: (): Promise<AdoptionSummary> => ipcRenderer.invoke('ragx:getAdoption'),
  onActivity: (cb: (events: ActivityEvent[]) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, events: ActivityEvent[]) => cb(events)
    ipcRenderer.on('ragx:activity', listener)
    return () => ipcRenderer.removeListener('ragx:activity', listener)
  },
  getProjectStatus: (projectId: string): Promise<unknown> => ipcRenderer.invoke('ragx:getProjectStatus', projectId),
  runTrial: (projectId: string): Promise<TrialResult> => ipcRenderer.invoke('ragx:runTrial', projectId),
  previewContext: (projectId: string, question: string): Promise<ContextPreview> =>
    ipcRenderer.invoke('ragx:previewContext', projectId, question),
  getIndexRuns: (projectId: string, offset: number): Promise<unknown> =>
    ipcRenderer.invoke('ragx:getIndexRuns', projectId, offset),
  runSecurityScan: (projectId: string): Promise<SecurityScanResult> =>
    ipcRenderer.invoke('ragx:runSecurityScan', projectId),
  getConnections: (): Promise<ConnectionCheck[]> => ipcRenderer.invoke('ragx:getConnections'),
  onConnections: (cb: (checks: ConnectionCheck[]) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, checks: ConnectionCheck[]) => cb(checks)
    ipcRenderer.on('ragx:connections', listener)
    return () => ipcRenderer.removeListener('ragx:connections', listener)
  },
  listJobs: (): Promise<JobView[]> => ipcRenderer.invoke('ragx:listJobs'),
  onJobs: (cb: (jobs: JobView[]) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, jobs: JobView[]) => cb(jobs)
    ipcRenderer.on('ragx:jobs', listener)
    return () => ipcRenderer.removeListener('ragx:jobs', listener)
  },
  enqueueJob: (req: JobRequest): Promise<JobView> => ipcRenderer.invoke('ragx:enqueueJob', req),
  cancelJob: (jobId: string): Promise<boolean> => ipcRenderer.invoke('ragx:cancelJob', jobId),
  pickFolder: (): Promise<{ token: string; path: string } | null> => ipcRenderer.invoke('ragx:pickFolder'),
  discover: (token: string): Promise<DiscoverResult> => ipcRenderer.invoke('ragx:discover', token),
  getSettings: (): Promise<PanelSettings> => ipcRenderer.invoke('ragx:getSettings'),
  setOnboardingDone: (done: boolean): Promise<void> => ipcRenderer.invoke('ragx:setOnboardingDone', done),
  setPricing: (pricing: Pricing | null): Promise<void> => ipcRenderer.invoke('ragx:setPricing', pricing),
  // Sem argumentos de propósito: nada que o renderer passe chega ao processo principal.
  runOllamaBenchmark: (): Promise<OllamaBenchmark> => ipcRenderer.invoke('ragx:run-ollama-benchmark'),
  getClaudeIntegration: (): Promise<ClaudeIntegration> => ipcRenderer.invoke('ragx:getClaudeIntegration'),
  setClaudeIntegration: (enabled: boolean): Promise<ClaudeIntegration> =>
    ipcRenderer.invoke('ragx:setClaudeIntegration', enabled),
  setClaudeProfile: (id: string, enabled: boolean): Promise<ClaudeIntegration> =>
    ipcRenderer.invoke('ragx:setClaudeProfile', id, enabled),
  addClaudeProfile: (token: string): Promise<ClaudeIntegration> => ipcRenderer.invoke('ragx:addClaudeProfile', token),
  removeClaudeProfile: (id: string): Promise<ClaudeIntegration> => ipcRenderer.invoke('ragx:removeClaudeProfile', id),
}

contextBridge.exposeInMainWorld('ragx', ragx)
