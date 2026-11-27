import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type {
  Account,
  ActivityEntry,
  AccountUsage,
  Conflict,
  EngineStatus,
  FolderSize,
  NewProfile,
  OAuthInfo,
  Profile,
  RemoteEntry,
  Settings,
  Snapshot,
  UpdateInfo,
} from "./types";
import { demoBackend } from "./demo";

export const isDesktop =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export type Backend = {
  engineStatus(): Promise<EngineStatus>;
  listAccounts(): Promise<Account[]>;
  connectAccount(
    provider: string,
    name: string,
    extra?: { url?: string; user?: string; pass?: string },
  ): Promise<Account>;
  listProfiles(): Promise<Profile[]>;
  createProfile(input: NewProfile): Promise<Profile>;
  updateProfile(profile: Profile): Promise<Profile>;
  deleteProfile(id: string): Promise<void>;
  deleteAccount(account: string): Promise<void>;
  startSync(id: string, resync?: boolean): Promise<Snapshot>;
  setPaused(paused: boolean, durationMin?: number): Promise<Snapshot>;
  stopAll(): Promise<Snapshot>;
  syncStatus(): Promise<Snapshot>;
  recentActivity(): Promise<ActivityEntry[]>;
  clearActivity(): Promise<void>;
  setTrayTheme(dark: boolean): Promise<void>;
  getSettings(): Promise<Settings>;
  saveSettings(settings: Settings): Promise<Settings>;
  setAutostart(enabled: boolean): Promise<boolean>;
  autostartEnabled(): Promise<boolean>;
  listRemote(account: string, path: string): Promise<RemoteEntry[]>;
  folderSize(account: string, path: string): Promise<FolderSize>;
  uploadFile(account: string, remoteDir: string, localPath: string): Promise<string>;
  downloadFile(account: string, remotePath: string, localDir: string): Promise<string>;
  scanConflicts(): Promise<Conflict[]>;
  resolveConflict(
    action: "remote" | "local" | "both",
    conflict: Conflict,
  ): Promise<Conflict[]>;
  listTrash(): Promise<import("./types").TrashItem[]>;
  restoreTrashItem(id: string, destinationDir: string): Promise<string>;
  emptyTrash(): Promise<void>;
  accountUsage(): Promise<AccountUsage[]>;
  // E-mail de cada conta (só as que dão para descobrir): a janela mostra o
  // endereço embaixo do nome, para não confundir "Google Drive 1" com "2".
  accountEmails(): Promise<Record<string, string>>;
  // Botão Cancelar da janela "aguardando autorização": o app desiste na hora.
  cancelAuthorization(): Promise<void>;
  revealPath(path: string): Promise<void>;
  openConfigFolder(): Promise<string>;
  saveDiagnostics(): Promise<string>;
  checkUpdate(): Promise<UpdateInfo | null>;
  installUpdate(url: string, fileName: string): Promise<string>;
  openUrl(url: string): Promise<void>;
  oauthInfo(): Promise<OAuthInfo>;
  // "Sair" com a pergunta feita pelo Rust: com sincronização em andamento a
  // janela volta à frente com as opções, em vez de matar o processo.
  requestQuit(): Promise<void>;
  // Encerra na hora, sem perguntar (a opção "Sair e interromper").
  quitApp(): Promise<void>;
  // Leva a janela para a bandeja ("Continuar em segundo plano").
  hideWindow(): Promise<void>;
};

const desktop: Backend = {
  engineStatus: () => invoke("engine_status"),
  listAccounts: () => invoke("list_accounts"),
  connectAccount: (provider, name, extra) =>
    invoke("connect_account", {
      provider,
      name,
      url: extra?.url,
      user: extra?.user,
      pass: extra?.pass,
    }),
  listProfiles: () => invoke("list_profiles"),
  createProfile: (input) => invoke("create_profile", { input }),
  updateProfile: (profile) => invoke("update_profile", { profile }),
  deleteProfile: (id) => invoke("delete_profile", { id }),
  deleteAccount: (account) => invoke("delete_account", { account }),
  startSync: (id, resync) => invoke("start_sync", { id, resync }),
  setPaused: (paused, durationMin) => invoke("set_paused", { paused, durationMin }),
  stopAll: () => invoke("stop_all"),
  syncStatus: () => invoke("sync_status"),
  recentActivity: () => invoke("recent_activity"),
  clearActivity: () => invoke("clear_activity"),
  setTrayTheme: (dark) => invoke("set_tray_theme", { dark }),
  getSettings: () => invoke("get_settings"),
  saveSettings: (settings) => invoke("save_settings", { settings }),
  setAutostart: (enabled) => invoke("set_autostart", { enabled }),
  autostartEnabled: () => invoke("autostart_enabled"),
  listRemote: (account, path) => invoke("list_remote", { account, path }),
  folderSize: (account, path) => invoke("folder_size", { account, path }),
  uploadFile: (account, remoteDir, localPath) =>
    invoke("upload_file", { account, remoteDir, localPath }),
  downloadFile: (account, remotePath, localDir) =>
    invoke("download_file", { account, remotePath, localDir }),
  scanConflicts: () => invoke("scan_conflicts"),
  resolveConflict: (action, conflict) =>
    invoke("resolve_conflict", {
      action,
      localFolder: conflict.localFolder,
      baseName: conflict.baseName,
      path1: conflict.path1,
      path2: conflict.path2,
    }),
  listTrash: () => invoke("list_trash"),
  restoreTrashItem: (id, destinationDir) => invoke("restore_trash_item", { id, destinationDir }),
  emptyTrash: () => invoke("empty_trash"),
  accountUsage: () => invoke("account_usage"),
  accountEmails: () => invoke("account_emails"),
  cancelAuthorization: () => invoke("cancel_authorization"),
  revealPath: (path) => invoke("reveal_path", { path }),
  openConfigFolder: () => invoke("open_config_folder"),
  saveDiagnostics: () => invoke("save_diagnostics"),
  checkUpdate: () => invoke("check_update"),
  installUpdate: (url, fileName) => invoke("install_update", { url, fileName }),
  openUrl: (url) => invoke("open_url", { url }),
  oauthInfo: () => invoke("oauth_info"),
  requestQuit: () => invoke("request_quit"),
  quitApp: () => invoke("quit_app"),
  hideWindow: () => invoke("hide_window"),
};

const demo: Backend = {
  engineStatus: () => demoBackend.engineStatus(),
  listAccounts: () => demoBackend.listAccounts(),
  connectAccount: (provider, name, extra) => demoBackend.connectAccount(provider, name, extra),
  listProfiles: () => demoBackend.listProfiles(),
  createProfile: (input) => demoBackend.createProfile(input),
  updateProfile: (profile) => demoBackend.updateProfile(profile),
  deleteProfile: (id) => demoBackend.deleteProfile(id),
  deleteAccount: (account) => demoBackend.deleteAccount(account),
  startSync: (id, resync) => demoBackend.startSync(id, resync),
  setPaused: (paused, durationMin) => demoBackend.setPaused(paused, durationMin),
  stopAll: () => demoBackend.stopAll(),
  syncStatus: () => demoBackend.syncStatus(),
  recentActivity: () => demoBackend.recentActivity(),
  clearActivity: () => demoBackend.clearActivity(),
  setTrayTheme: async () => {},
  getSettings: () => demoBackend.getSettings(),
  saveSettings: (settings) => demoBackend.saveSettings(settings),
  setAutostart: (enabled) => demoBackend.setAutostart(enabled),
  autostartEnabled: () => demoBackend.autostartEnabled(),
  listRemote: (account, path) => demoBackend.listRemote(account, path),
  folderSize: (account, path) => demoBackend.folderSize(account, path),
  uploadFile: (account, remoteDir, localPath) =>
    demoBackend.uploadFile(account, remoteDir, localPath),
  downloadFile: (account, remotePath, localDir) =>
    demoBackend.downloadFile(account, remotePath, localDir),
  scanConflicts: () => demoBackend.scanConflicts(),
  resolveConflict: (action, conflict) => demoBackend.resolveConflict(action, conflict),
  listTrash: () => demoBackend.listTrash(),
  restoreTrashItem: (id, destinationDir) => demoBackend.restoreTrashItem(id, destinationDir),
  emptyTrash: () => demoBackend.emptyTrash(),
  accountUsage: () => demoBackend.accountUsage(),
  accountEmails: () => demoBackend.accountEmails(),
  cancelAuthorization: async () => {},
  revealPath: () => demoBackend.revealPath(),
  openConfigFolder: () => demoBackend.openConfigFolder(),
  saveDiagnostics: () => demoBackend.saveDiagnostics(),
  checkUpdate: () => demoBackend.checkUpdate(),
  installUpdate: () => demoBackend.installUpdate(),
  openUrl: (url) => demoBackend.openUrl(url),
  oauthInfo: () => demoBackend.oauthInfo(),
  requestQuit: () => demoBackend.quitApp(),
  quitApp: () => demoBackend.quitApp(),
  hideWindow: async () => {},
};

export const api: Backend = isDesktop ? desktop : demo;

/** Escuta eventos do backend nativo; no modo demo não há eventos. */
export function subscribe(
  event: string,
  handler: (payload: unknown) => void,
): () => void {
  if (!isDesktop) return () => {};
  let dispose: (() => void) | undefined;
  let cancelled = false;
  listen(event, (message) => handler(message.payload))
    .then((unlisten) => {
      if (cancelled) unlisten();
      else dispose = unlisten;
    })
    .catch(() => {});
  return () => {
    cancelled = true;
    dispose?.();
  };
}

export function errorMessage(error: unknown): string {
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "message" in error) {
    return String((error as { message: unknown }).message);
  }
  return "Algo deu errado.";
}
