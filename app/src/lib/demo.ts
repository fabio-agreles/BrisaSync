import type {
  Account,
  ActivityEntry,
  Conflict,
  NewProfile,
  Profile,
  RemoteEntry,
  Settings,
  Snapshot,
  Transfer,
} from "./types";

const now = () => Date.now();

const delay = (ms = 90) => new Promise((resolve) => setTimeout(resolve, ms));

const GB = 1024 ** 3;
const MB = 1024 ** 2;

const initialTransfers: Transfer[] = [
  {
    name: "Projetos/Relatório anual 2026.pdf",
    size: 48 * MB,
    bytes: 21 * MB,
    percent: 43,
    speed: 2.1 * MB,
    eta: 14,
  },
  {
    name: "Fotos/viagem/serra-do-rio.jpg",
    size: 12 * MB,
    bytes: 9 * MB,
    percent: 76,
    speed: 1.4 * MB,
    eta: 3,
  },
  {
    name: "OneDrive/Documentos/notas-reunião.md",
    size: 240 * 1024,
    bytes: 90 * 1024,
    percent: 37,
    speed: 120 * 1024,
    eta: 2,
  },
];

/**
 * Backend de demonstração: simula o motor para que a UI possa ser aberta
 * no navegador (npm run dev) sem rclone, contas ou OAuth.
 */
class DemoBackend {
  accounts: Account[] = [
    { name: "pessoal", provider: "drive", label: "Google Drive", clientOrigem: "rclone" },
    { name: "trabalho", provider: "onedrive", label: "OneDrive", clientOrigem: "rclone" },
  ];

  profiles: Profile[] = [
    {
      id: "demo-1",
      account: "pessoal",
      remotePath: "Projetos",
      localPath: "~/BrisaSync/Projetos",
      enabled: true,
      resyncNeeded: false,
      lastSync: now() - 6 * 60_000,
      lastError: null,
      lastBytes: 3.4 * GB,
    },
    {
      id: "demo-2",
      account: "pessoal",
      remotePath: "Fotos",
      localPath: "~/BrisaSync/Fotos",
      enabled: true,
      resyncNeeded: false,
      lastSync: now() - 2 * 60 * 60_000,
      lastError: null,
      lastBytes: 12.8 * GB,
    },
    {
      id: "demo-3",
      account: "trabalho",
      remotePath: "Documentos",
      localPath: "~/BrisaSync/Trabalho",
      enabled: true,
      resyncNeeded: false,
      lastSync: now() - 26 * 60 * 60_000,
      lastError: null,
      lastBytes: 980 * MB,
    },
    {
      id: "demo-4",
      account: "trabalho",
      remotePath: "Backup antigo",
      localPath: "~/BrisaSync/Backup antigo",
      enabled: false,
      resyncNeeded: true,
      lastSync: null,
      lastError: null,
      lastBytes: 0,
    },
  ];

  activity: ActivityEntry[] = [
    {
      id: "a1",
      kind: "sync",
      title: "Sincronização concluída",
      detail: "pessoal:Projetos está em dia",
      at: now() - 6 * 60_000,
      profile: "demo-1",
      files: [
        { name: "Orçamento 2026.ods", action: "sent" },
        { name: "briefing/escopo.md", action: "sent" },
        { name: "briefing/reunião-12.md", action: "received" },
        { name: "rascunho-antigo.txt", action: "deletedRemote" },
      ],
    },
    {
      id: "a2",
      kind: "upload",
      title: "3 arquivos enviados",
      detail: "pessoal:Fotos · 41 MB",
      at: now() - 2 * 60 * 60_000,
      profile: "demo-2",
      files: [
        { name: "2026/01/praia.jpg", action: "sent" },
        { name: "2026/01/trilha.jpg", action: "sent" },
        { name: "2026/01/vídeo.mp4", action: "sent" },
      ],
    },
    {
      id: "a3",
      kind: "conflict",
      title: "Conflito detectado",
      detail: "Relatório final.docx tem duas versões",
      at: now() - 5 * 60 * 60_000,
      profile: "demo-1",
    },
    {
      id: "a4",
      kind: "error",
      title: "Falha na sincronização",
      detail: "trabalho:Documentos · cota da conta excedida",
      at: now() - 26 * 60 * 60_000,
      profile: "demo-3",
    },
    {
      id: "a5",
      kind: "account",
      title: "Conta conectada",
      detail: "OneDrive · trabalho",
      at: now() - 4 * 86_400_000,
      profile: null,
    },
  ];

  settings: Settings = {
    theme: "light",
    bandwidthUp: "",
    bandwidthDown: "",
    notifications: true,
    ignoreRules: ["*.tmp", ".git/", "node_modules/"],
    proxy: "",
    docsConversion: false,
    symlinks: false,
    autoRetry: true,
    autoSync: true,
    syncIntervalMin: 5,
    driveClientId: "",
    driveClientSecret: "",
    language: "pt",
    closeQuits: false,
  };

  private paused = false;
  private running = true;
  private transfers: Transfer[] = initialTransfers.map((item) => ({ ...item }));
  private bytes = initialTransfers.reduce((sum, item) => sum + item.bytes, 0);
  private totalBytes = initialTransfers.reduce((sum, item) => sum + item.size, 0);

  async engineStatus() {
    await delay();
    return {
      available: true,
      version: "v1.75.2 (demonstração)",
      binary: "/usr/bin/rclone",
      accounts: this.accounts.length,
    };
  }

  async listAccounts() {
    await delay();
    return [...this.accounts];
  }

  async connectAccount(
    provider: string,
    name: string,
    _extra?: { url?: string; user?: string; pass?: string },
  ) {
    await delay(700);
    const label =
      provider === "drive"
        ? "Google Drive"
        : provider === "onedrive"
          ? "OneDrive"
          : provider === "dropbox"
            ? "Dropbox"
            : provider === "nextcloud"
              ? "Nextcloud"
              : provider;
    const account: Account = {
      name: name.trim() || `${label} ${this.accounts.length + 1}`,
      provider,
      label,
      clientOrigem:
        provider === "drive" && Boolean(this.settings.driveClientId.trim())
          ? "usuario"
          : "rclone",
    };
    this.accounts = [...this.accounts, account];
    this.pushActivity("account", "Conta conectada", `${label} · ${account.name}`, null);
    return account;
  }

  async listProfiles() {
    await delay();
    return this.profiles.map((profile) => ({ ...profile }));
  }

  async createProfile(input: NewProfile) {
    await delay(200);
    const profile: Profile = {
      id: `demo-${now()}`,
      account: input.account,
      remotePath: input.remotePath,
      localPath: input.localPath,
      enabled: input.enabled,
      resyncNeeded: true,
      lastSync: null,
      lastError: null,
      lastBytes: 0,
    };
    this.profiles = [...this.profiles, profile];
    this.pushActivity("info", "Pasta adicionada", `${profile.remotePath} → ${profile.localPath}`, profile.id);
    return { ...profile };
  }

  async updateProfile(profile: Profile) {
    await delay(120);
    const prev = this.profiles.find((item) => item.id === profile.id);
    const excludedChanged =
      JSON.stringify(prev?.excludedFolders ?? []) !==
      JSON.stringify(profile.excludedFolders ?? []);
    const next = excludedChanged ? { ...profile, resyncNeeded: true } : { ...profile };
    this.profiles = this.profiles.map((item) => (item.id === profile.id ? next : item));
    return next;
  }

  async deleteProfile(id: string) {
    await delay(120);
    this.profiles = this.profiles.filter((item) => item.id !== id);
  }

  async startSync(id: string, resync = false) {
    await delay(220);
    this.paused = false;
    this.running = true;
    this.transfers = initialTransfers.map((item) => ({
      ...item,
      bytes: 0,
      percent: 0,
    }));
    this.bytes = 0;
    this.totalBytes = this.transfers.reduce((sum, item) => sum + item.size, 0);
    const profile = this.profiles.find((item) => item.id === id);
    this.pushActivity(
      resync ? "sync" : "sync",
      resync ? "Ressincronização iniciada" : "Sincronização iniciada",
      profile ? `${profile.account}:${profile.remotePath} ↔ ${profile.localPath}` : "pasta",
      id,
    );
    return this.snapshot();
  }

  async setPaused(paused: boolean) {
    await delay(150);
    this.paused = paused;
    this.running = false;
    this.pushActivity(
      "info",
      paused ? "Sincronização pausada" : "Sincronização retomada",
      paused ? "Todas as tarefas foram paradas." : "As pastas ativas voltaram a sincronizar.",
      null,
    );
    return this.snapshot();
  }

  async stopAll() {
    await delay(120);
    this.running = false;
    return this.snapshot();
  }

  async syncStatus() {
    await delay(40);
    this.advance();
    return this.snapshot();
  }

  async recentActivity() {
    await delay();
    return [...this.activity].sort((left, right) => right.at - left.at);
  }

  async clearActivity() {
    await delay(80);
    this.activity = [];
  }

  async getSettings() {
    await delay();
    return { ...this.settings };
  }

  async saveSettings(settings: Settings) {
    await delay(120);
    this.settings = { ...settings };
    return { ...this.settings };
  }

  async deleteAccount(account: string) {
    await delay(120);
    if (this.profiles.some((profile) => profile.account === account)) {
      throw new Error("remova antes as pastas que usam esta conta.");
    }
    this.accounts = this.accounts.filter((item) => item.name !== account);
  }

  async setAutostart(enabled: boolean) {
    await delay(80);
    return enabled;
  }

  async autostartEnabled() {
    await delay(60);
    return false;
  }

  async folderSize(account: string, path: string) {
    await delay(160);
    const listing = TREE[`${account}:${path}`] ?? [];
    const bytes = listing.reduce((sum, entry) => sum + entry.size, 0);
    return { count: listing.length, bytes, sizeless: 0 };
  }

  async uploadFile(account: string, remoteDir: string, localPath: string) {
    await delay(600);
    const name = localPath.split("/").pop() ?? "arquivo";
    const entry = {
      name,
      path: remoteDir ? `${remoteDir}/${name}` : name,
      size: 512 * 1024,
      isDir: false,
      modified: new Date().toISOString(),
    };
    const key = `${account}:${remoteDir}`;
    TREE[key] = [entry, ...(TREE[key] ?? [])];
    return entry.path;
  }

  async downloadFile(_account: string, remotePath: string, localDir: string) {
    await delay(600);
    return `${localDir}/${remotePath.split("/").pop() ?? "arquivo"}`;
  }

  async listRemote(account: string, path: string) {
    await delay(180);
    const key = `${account}:${path}`;
    const listing = TREE[key] ?? [];
    return listing.map((entry) => ({ ...entry }));
  }

  private conflicts: Conflict[] = [
    {
      id: "demo::Relatório final.docx",
      folder: "pessoal:Projetos",
      localFolder: "~/BrisaSync/Projetos",
      baseName: "Relatório final.docx",
      path1: "~/BrisaSync/Projetos/Relatório final.docx..path1",
      path2: "~/BrisaSync/Projetos/Relatório final.docx..path2",
      path1Size: 2.4 * MB,
      path2Size: 2.7 * MB,
      path1Modified: now() - 5 * 60 * 60_000,
      path2Modified: now() - 40 * 60_000,
    },
  ];

  async scanConflicts(): Promise<Conflict[]> {
    await delay(200);
    return this.conflicts.map((conflict) => ({ ...conflict }));
  }

  async resolveConflict(
    action: "remote" | "local" | "both",
    conflict: Conflict,
  ): Promise<Conflict[]> {
    await delay(350);
    this.conflicts = this.conflicts.filter((item) => item.id !== conflict.id);
    this.pushActivity(
      "conflict",
      "Conflito resolvido",
      `${conflict.baseName} · ${
        action === "remote"
          ? "mantida a versão da nuvem"
          : action === "local"
            ? "mantida a versão local"
            : "mantidas as duas versões"
      }`,
      null,
    );
    if (this.profiles.length > 0) {
      void this.startSync(this.profiles[0].id);
    }
    return this.conflicts.map((item) => ({ ...item }));
  }

  async accountEmails() {
    await delay(60);
    // O OneDrive fica de fora de propósito: nem toda conta tem e-mail legível, e
    // a interface precisa ficar bem sem ele.
    return { pessoal: "ana.silva@gmail.com" };
  }

  async accountUsage() {
    await delay(120);
    return [
      {
        account: "pessoal",
        label: "Google Drive",
        provider: "drive",
        total: 100 * GB,
        used: 38.4 * GB,
        free: 61.6 * GB,
        error: null,
        stale: false,
      },
      {
        account: "trabalho",
        label: "OneDrive",
        provider: "onedrive",
        total: 1024 * GB,
        used: 212 * GB,
        free: 812 * GB,
        error: null,
        stale: false,
      },
    ];
  }

  async revealPath() {
    await delay(40);
  }

  async openConfigFolder() {
    await delay(40);
    return "~/.config/nuvem";
  }

  async saveDiagnostics() {
    await delay(120);
    return "~/Documentos/nuvem-diagnostico-2026-10-30-1830.txt";
  }

  async checkUpdate() {
    await delay(300);
    return null;
  }

  async installUpdate() {
    await delay(400);
    return "/tmp/BrisaSync-demo.deb";
  }

  async openUrl() {
    await delay(40);
  }

  async oauthInfo() {
    await delay(30);
    return { fonte: "rclone" as const, clientId: null };
  }

  async quitApp() {
    await delay(40);
  }

  private advance() {
    if (this.paused || !this.running) return;

    this.transfers = this.transfers.map((transfer) => {
      const step = 4 + Math.random() * 9;
      const percent = Math.min(100, transfer.percent + step);
      const bytes = Math.round((transfer.size * percent) / 100);
      return {
        ...transfer,
        percent,
        bytes,
        speed: transfer.speed,
        eta: percent >= 100 ? 0 : Math.max(1, Math.round(((100 - percent) / 100) * transfer.size / transfer.speed)),
      };
    });

    this.bytes = this.transfers.reduce((sum, item) => sum + item.bytes, 0);
    const done = this.transfers.every((transfer) => transfer.percent >= 100);
    if (done) {
      this.running = false;
      const stamp = now();
      this.profiles = this.profiles.map((profile) =>
        profile.enabled ? { ...profile, lastSync: stamp, resyncNeeded: false, lastError: null } : profile,
      );
      this.pushActivity("sync", "Sincronização concluída", "Todas as pastas ativas estão em dia.", null);
      this.transfers = [];
    }
  }

  private pushActivity(kind: string, title: string, detail: string, profile: string | null) {
    this.activity = [
      { id: `demo-${now()}-${Math.random().toString(16).slice(2, 6)}`, kind, title, detail, at: now(), profile },
      ...this.activity,
    ].slice(0, 200);
  }

  private snapshot(): Snapshot {
    const speed = this.transfers.reduce((sum, item) => sum + item.speed, 0);
    return {
      engineReady: true,
      paused: this.paused,
      running: this.running && !this.paused,
      speed: this.running && !this.paused ? speed : 0,
      bytes: this.bytes,
      totalBytes: this.totalBytes,
      errors: 0,
      transfers: this.running && !this.paused ? this.transfers.map((item) => ({ ...item })) : [],
      jobs: this.running && !this.paused ? this.transfers.length : 0,
    };
  }
}

const TREE: Record<string, RemoteEntry[]> = {
  "pessoal:": [
    { name: "Projetos", path: "Projetos", size: 0, isDir: true, modified: "2026-10-28T09:12:00Z" },
    { name: "Fotos", path: "Fotos", size: 0, isDir: true, modified: "2026-10-27T18:03:00Z" },
    { name: "Documentos", path: "Documentos", size: 0, isDir: true, modified: "2026-10-20T11:45:00Z" },
    { name: "planilha-orçamento.xlsx", path: "planilha-orçamento.xlsx", size: 84 * 1024, isDir: false, modified: "2026-10-28T08:40:00Z" },
  ],
  "pessoal:Projetos": [
    { name: "BrisaSync", path: "Projetos/BrisaSync", size: 0, isDir: true, modified: "2026-10-28T09:12:00Z" },
    { name: "Relatório anual 2026.pdf", path: "Projetos/Relatório anual 2026.pdf", size: 4.8 * MB, isDir: false, modified: "2026-10-28T09:12:00Z" },
    { name: "briefing.md", path: "Projetos/briefing.md", size: 18 * 1024, isDir: false, modified: "2026-10-24T14:20:00Z" },
  ],
  "pessoal:Projetos/BrisaSync": [
    { name: "design-spec.fig", path: "Projetos/BrisaSync/design-spec.fig", size: 22 * MB, isDir: false, modified: "2026-10-28T07:58:00Z" },
    { name: "notas.txt", path: "Projetos/BrisaSync/notas.txt", size: 2 * 1024, isDir: false, modified: "2026-10-27T22:10:00Z" },
  ],
  "trabalho:": [
    { name: "Documentos", path: "Documentos", size: 0, isDir: true, modified: "2026-10-27T16:30:00Z" },
    { name: "Backup antigo", path: "Backup antigo", size: 0, isDir: true, modified: "2025-12-01T10:00:00Z" },
  ],
};

export const demoBackend = new DemoBackend();
