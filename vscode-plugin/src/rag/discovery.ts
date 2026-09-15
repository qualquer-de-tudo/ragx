/**
 * Descoberta do projeto RAGX no workspace (§5).
 *
 * Só olha por NOMES de arquivo — nunca abre conteúdo. Um detector que lesse
 * arquivos para decidir se o projeto existe seria a primeira coisa a violar a
 * regra que o plugin inteiro promete respeitar.
 */

import * as vscode from 'vscode';

export interface Discovery {
  found: boolean;
  root?: vscode.Uri;
  /** Sinais encontrados, na ordem em que a UI deve mostrá-los. */
  markers: string[];
  /** `true` quando há configuração mas nenhum índice — pede `ragx index .`. */
  needsIndex: boolean;
}

const MARKERS = [
  { file: 'ragx.toml', weight: 3 },
  { file: 'knowledge/manifest.json', weight: 2 },
  { file: '.ragx/knowledge.db', weight: 2 },
  { file: 'rag.toml', weight: 1 },
] as const;

export async function discover(): Promise<Discovery> {
  const folders = vscode.workspace.workspaceFolders ?? [];
  for (const folder of folders) {
    const achados: string[] = [];
    let peso = 0;
    let temIndice = false;

    for (const marker of MARKERS) {
      const uri = vscode.Uri.joinPath(folder.uri, ...marker.file.split('/'));
      if (await exists(uri)) {
        achados.push(marker.file);
        peso += marker.weight;
        if (marker.file !== 'ragx.toml' && marker.file !== 'rag.toml') {
          temIndice = true;
        }
      }
    }
    if (peso > 0) {
      return {
        found: true,
        root: folder.uri,
        markers: achados,
        needsIndex: !temIndice,
      };
    }
  }
  return { found: false, markers: [], needsIndex: false };
}

async function exists(uri: vscode.Uri): Promise<boolean> {
  try {
    await vscode.workspace.fs.stat(uri);
    return true;
  } catch {
    return false;
  }
}

/**
 * Caminho relativo à raiz do projeto, em POSIX.
 *
 * É a chave que o RAGX usa para consultar o índice — não um caminho de
 * arquivo. Devolve `undefined` para qualquer coisa fora da raiz, porque não
 * existe resposta correta para isso.
 */
export function toRelPath(root: vscode.Uri, file: vscode.Uri): string | undefined {
  const raiz = root.fsPath.replace(/\\/g, '/').replace(/\/$/, '');
  const alvo = file.fsPath.replace(/\\/g, '/');
  if (!alvo.toLowerCase().startsWith(raiz.toLowerCase() + '/')) return undefined;
  return alvo.slice(raiz.length + 1);
}
