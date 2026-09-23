import { contextBridge, ipcRenderer } from 'electron'
import type { Snapshot } from '../src/types/ragx-bridge'

contextBridge.exposeInMainWorld('ragx', {
  getSnapshot: (): Promise<Snapshot> => ipcRenderer.invoke('ragx:get-snapshot'),
  onSnapshot: (cb: (snapshot: Snapshot) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, snapshot: Snapshot) => cb(snapshot)
    ipcRenderer.on('ragx:snapshot', listener)
    return () => ipcRenderer.removeListener('ragx:snapshot', listener)
  },
})
