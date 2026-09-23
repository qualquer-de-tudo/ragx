import { contextBridge } from 'electron'

// A ponte real (leitura de projetos/telemetria) entra na Task 2. Por ora,
// so confirma que o preload carregou, pra Task 1 validar a integracao.
contextBridge.exposeInMainWorld('ragx', {
  ping: () => 'pong',
})
