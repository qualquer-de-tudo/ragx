import { contextBridge, ipcRenderer } from 'electron'
import type {
  ConnectionCheck,
  DiscoverItem,
  JobRequest,
  JobView,
  PanelSettings,
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
  getProjectStatus: (projectId: string): Promise<unknown> => ipcRenderer.invoke('ragx:getProjectStatus', projectId),
  runTrial: (projectId: string): Promise<TrialResult> => ipcRenderer.invoke('ragx:runTrial', projectId),
  runSecurityScan: (projectId: string): Promise<SecurityScanResult> =>
    ipcRenderer.invoke('ragx:runSecurityScan', projectId),
  getConnections: (): Promise<ConnectionCheck[]> => ipcRenderer.invoke('ragx:getConnections'),
  listJobs: (): Promise<JobView[]> => ipcRenderer.invoke('ragx:listJobs'),
  onJobs: (cb: (jobs: JobView[]) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, jobs: JobView[]) => cb(jobs)
    ipcRenderer.on('ragx:jobs', listener)
    return () => ipcRenderer.removeListener('ragx:jobs', listener)
  },
  enqueueJob: (req: JobRequest): Promise<JobView> => ipcRenderer.invoke('ragx:enqueueJob', req),
  cancelJob: (jobId: string): Promise<boolean> => ipcRenderer.invoke('ragx:cancelJob', jobId),
  pickFolder: (): Promise<{ token: string; path: string } | null> => ipcRenderer.invoke('ragx:pickFolder'),
  discover: (token: string): Promise<DiscoverItem[]> => ipcRenderer.invoke('ragx:discover', token),
  getSettings: (): Promise<PanelSettings> => ipcRenderer.invoke('ragx:getSettings'),
  setOnboardingDone: (done: boolean): Promise<void> => ipcRenderer.invoke('ragx:setOnboardingDone', done),
}

contextBridge.exposeInMainWorld('ragx', ragx)
