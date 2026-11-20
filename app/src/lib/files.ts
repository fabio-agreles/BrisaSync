import { t } from "./i18n";
import type { FileChange } from "./types";

/// Cada ação tem rótulo no singular e no plural; a ordem é a de leitura na tela.
export const ACOES: { action: FileChange["action"]; um: string; varios: string }[] = [
  { action: "sent", um: "enviado", varios: "enviados" },
  { action: "received", um: "baixado", varios: "baixados" },
  { action: "deletedRemote", um: "apagado na nuvem", varios: "apagados na nuvem" },
  { action: "deletedLocal", um: "apagado aqui", varios: "apagados aqui" },
];

export type ResumoAcao = { action: FileChange["action"]; um: string; varios: string; quantos: number };

/// Só as ações que aconteceram, com a contagem.
export function resumo(files: FileChange[]): ResumoAcao[] {
  return ACOES.map((acao) => {
    const quantos = files.filter((file) => file.action === acao.action).length;
    return { ...acao, quantos };
  }).filter((item) => item.quantos > 0);
}

/// Os arquivos separados por ação, na ordem de `ACOES`.
export function grupos(files: FileChange[]) {
  return ACOES.map((acao) => ({
    ...acao,
    itens: files.filter((file) => file.action === acao.action),
  })).filter((grupo) => grupo.itens.length > 0);
}

/// `2 enviados · 1 baixado` — para onde não cabe a lista de etiquetas.
export function resumoTexto(files: FileChange[]): string {
  return resumo(files)
    .map((item) => `${item.quantos} ${t(item.quantos === 1 ? item.um : item.varios)}`)
    .join(" · ");
}
