import pacote from "../../package.json";

/**
 * Nome que aparece para quem usa o app.
 *
 * O **identificador** é `app.brisasync.BrisaSync` e o binário é `brisasync`.
 * O nome de exibição é só isto — e precisa bater com o site e com a
 * marca no console do Google.
 */
export const NOME = "BrisaSync";

/** Versão do `package.json`, a mesma que o Tauri põe no binário. */
export const VERSAO: string = pacote.version;
