/** Formas dos ícones do painel (RAGX-0179), em grade 24x24, para traço (`stroke`) sem preenchimento. Fica em `.ts` por
 * causa da regra `react-refresh/only-export-components`: o componente está em `Icon.tsx`. */
export type Shape =
  | { path: string }
  | { rect: [x: number, y: number, width: number, height: number, rx: number] }
  | { circle: [cx: number, cy: number, r: number] }

export const ICONS = {
  close: [{ path: 'M6 6l12 12M18 6L6 18' }],
  back: [{ path: 'M15 5l-7 7 7 7' }],
  search: [{ circle: [11, 11, 6.5] }, { path: 'm16 16 4 4' }],
  queue: [{ path: 'M5 7h14M5 12h14M5 17h9' }],
  branch: [
    { circle: [6, 5, 2.2] },
    { circle: [6, 19, 2.2] },
    { circle: [18, 7, 2.2] },
    { path: 'M6 7.2v9.6' },
    { path: 'M18 9.2c0 5-6 4-11 7.8' },
  ],
  // Navegação
  projects: [{ rect: [4, 4, 7, 7, 1.5] }, { rect: [13, 4, 7, 7, 1.5] }, { rect: [4, 13, 7, 7, 1.5] }, { rect: [13, 13, 7, 7, 1.5] }],
  activity: [{ path: 'M3 12h4l2.5-6 5 12 2.5-6h4' }],
  connections: [
    { circle: [6, 12, 2.5] },
    { circle: [18, 6, 2.5] },
    { circle: [18, 18, 2.5] },
    { path: 'M8.2 10.8 15.8 7.2M8.2 13.2l7.6 3.6' },
  ],
  how: [{ circle: [12, 12, 8.5] }, { path: 'M9.6 9.6a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.6' }, { path: 'M12 16.9v.1' }],
  // Serviços das conexões
  ragx: [{ rect: [3.5, 5, 17, 14, 2.5] }, { path: 'm7.5 10 2.5 2-2.5 2M12.5 14.5h4' }],
  claude: [{ path: 'M12 3.5v17M3.5 12h17M6 6l12 12M18 6 6 18' }],
  ollama: [{ rect: [6, 6, 12, 12, 2] }, { path: 'M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3' }],
  pending: [{ circle: [12, 12, 7] }],
} as const satisfies Record<string, readonly Shape[]>

export type IconName = keyof typeof ICONS
