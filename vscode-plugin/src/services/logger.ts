/**
 * Canal de saída. É onde o detalhe vive — a UI mostra o que dá para agir (§39).
 */

import * as vscode from 'vscode';

let canal: vscode.OutputChannel | undefined;

export function logger(): vscode.OutputChannel {
  if (!canal) canal = vscode.window.createOutputChannel('RAGX Knowledge');
  return canal;
}

export function log(linha: string): void {
  const agora = new Date().toISOString().slice(11, 19);
  logger().appendLine(`[${agora}] ${linha}`);
}

export function logError(escopo: string, err: unknown): void {
  const detalhe = err instanceof Error ? (err.stack ?? err.message) : String(err);
  log(`ERRO ${escopo}: ${detalhe}`);
}

export function showLogs(): void {
  logger().show(true);
}

export function disposeLogger(): void {
  canal?.dispose();
  canal = undefined;
}
