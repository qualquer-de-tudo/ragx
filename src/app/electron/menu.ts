import type { MenuItemConstructorOptions } from 'electron'

/**
 * Menu de aplicacao minimo, em portugues (RAGX-0194). Sem ele o Electron usa o menu padrao (Alt abre Recarregar e
 * Ferramentas do desenvolvedor). Fica Edicao (copiar e colar nos campos), Exibir so com o zoom (Ctrl+= e Ctrl+-
 * continuam valendo) e Sair. Recarregar e DevTools so entram com `devTools`.
 */
export function buildMenuTemplate(opts: { devTools: boolean }): MenuItemConstructorOptions[] {
  const view: MenuItemConstructorOptions[] = [
    { role: 'resetZoom', label: 'Tamanho padrão' },
    { role: 'zoomIn', label: 'Aumentar' },
    { role: 'zoomOut', label: 'Diminuir' },
    { type: 'separator' },
    { role: 'togglefullscreen', label: 'Tela cheia' },
  ]
  if (opts.devTools) {
    view.push(
      { type: 'separator' },
      { role: 'reload', label: 'Recarregar' },
      { role: 'forceReload', label: 'Recarregar sem cache' },
      { role: 'toggleDevTools', label: 'Ferramentas do desenvolvedor' },
    )
  }
  return [
    {
      label: 'Edição',
      submenu: [
        { role: 'undo', label: 'Desfazer' },
        { role: 'redo', label: 'Refazer' },
        { type: 'separator' },
        { role: 'cut', label: 'Recortar' },
        { role: 'copy', label: 'Copiar' },
        { role: 'paste', label: 'Colar' },
        { role: 'selectAll', label: 'Selecionar tudo' },
      ],
    },
    { label: 'Exibir', submenu: view },
    { label: 'Sair', role: 'quit' },
  ]
}
