export type Account = {
  name: string;
  provider: string;
  label: string;
  /** Projeto OAuth que autorizou a conta: o do rclone (cota estourada), o do
   *  BrisaSync (embutido no build) ou o do próprio usuário. */
  clientOrigem: "rclone" | "brisasync" | "usuario";
};

export type Profile = {
  id: string;
  account: string;
  remotePath: string;
  localPath: string;
  enabled: boolean;
  resyncNeeded: boolean;
  lastSync: number | null;
  lastError: string | null;
  lastBytes: number;
  excludedFolders?: string[];
  syncIntervalMin?: number | null;
};

export type NewProfile = {
  account: string;
  remotePath: string;
  localPath: string;
  enabled: boolean;
  excludedFolders?: string[];
};

export type Transfer = {
  name: string;
  size: number;
  bytes: number;
  percent: number;
  speed: number;
  eta: number | null;
};

export type Snapshot = {
  engineReady: boolean;
  paused: boolean;
  pauseUntil?: number | null;
  running: boolean;
  speed: number;
  bytes: number;
  totalBytes: number;
  errors: number;
  transfers: Transfer[];
  jobs: number;
};

export type EngineStatus = {
  available: boolean;
  version: string | null;
  binary: string | null;
  accounts: number;
};

export type FileChange = {
  name: string;
  action: "sent" | "received" | "deletedRemote" | "deletedLocal";
};

export type ActivityEntry = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  at: number;
  profile: string | null;
  /** O que cada arquivo fez nesta sincronização (vazio = nada mudou). */
  files?: FileChange[];
};

export type Settings = {
  theme: string;
  bandwidthUp: string;
  bandwidthDown: string;
  notifications: boolean;
  ignoreRules: string[];
  proxy: string;
  docsConversion: boolean;
  symlinks: boolean;
  autoRetry: boolean;
  autoSync: boolean;
  syncIntervalMin: number;
  /** Credenciais OAuth próprias do Google Drive; vazias = projeto do rclone. */
  driveClientId: string;
  driveClientSecret: string;
  /** Idioma da interface: "pt" (padrão) ou "en". */
  language: string;
  /** Fechar a janela encerra o app (padrão: vai para a bandeja). */
  closeQuits: boolean;
  /** Política de conflito: "ask" (padrão), "newer", "remote" ou "local". */
  conflictPolicy: "ask" | "newer" | "remote" | "local";
};

export type FolderSize = {
  count: number;
  bytes: number;
  sizeless: number;
};

export type RemoteEntry = {
  name: string;
  path: string;
  size: number;
  isDir: boolean;
  modified: string | null;
};

export type Conflict = {
  id: string;
  folder: string;
  localFolder: string;
  baseName: string;
  path1: string | null;
  path2: string | null;
  path1Size: number | null;
  path2Size: number | null;
  path1Modified: number | null;
  path2Modified: number | null;
};

export type TrashItem = {
  id: string;
  name: string;
  relativePath: string;
  size: number;
  deletedAt: number;
  profileId: string | null;
};

export type AccountUsage = {
  account: string;
  label: string;
  provider: string;
  total: number | null;
  used: number | null;
  free: number | null;
  error: string | null;
  /** Os números vieram de uma leitura anterior (a atual falhou). */
  stale: boolean;
};

export type ViewId =
  | "dashboard"
  | "files"
  | "folders"
  | "activity"
  | "conflicts"
  | "settings";

export type UpdateInfo = {
  /** Versão publicada, sem o `v` do tag. */
  version: string;
  /** Página da release, para abrir no navegador. */
  url: string;
  /** URL direta do pacote compatível com este sistema (quando disponível). */
  assetUrl?: string | null;
  /** Nome do arquivo do pacote compatível. */
  assetName?: string | null;
};

/** Qual projeto OAuth do Google está em uso no Google Drive. */
export type OAuthInfo = {
  /** "usuario" (credenciais coladas em Ajustes), "brisasync" (projeto embutido no
   *  build) ou "rclone" (projeto compartilhado, com cota estourada). */
  fonte: "usuario" | "brisasync" | "rclone";
  /** client_id em vigor — público, vai na URL de autorização. */
  clientId: string | null;
};
