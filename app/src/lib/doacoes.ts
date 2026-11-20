// Texto da tela de doações. A chave do Pix e o BR Code ("copia e cola") vêm de
// ./pix.ts, que é gerado por scripts/gerar-pix.sh junto com o QR code — assim o
// QR da tela e o texto copiado nunca saem de sincronia.

export { CHAVE_PIX, PIX_COPIA_E_COLA } from "./pix";

export const DOACAO_TITULO = "Ajude a manter o projeto";

export const DOACAO_RESUMO =
  "Gratuito e de código aberto. Se ele é útil para você, considere uma contribuição voluntária via Pix.";

export const DOACAO_PARAGRAFOS = [
  "Este aplicativo é gratuito e de código aberto. Seu desenvolvimento envolve investimento financeiro, tempo e dedicação.",
  "Se ele é útil para você, considere fazer uma contribuição voluntária via Pix. Seu apoio ajuda a manter o projeto e a desenvolver novas melhorias.",
  "Obrigado por fazer parte dessa história!",
];
