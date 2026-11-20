import { useState } from "react";
import { Icon } from "../components/Icons";
import { Modal } from "../components/Modal";
import { resumoTexto } from "../lib/files";
import { formatBytes, formatEta, formatSpeed, relativeTime } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Account, AccountUsage, ActivityEntry, Profile, Snapshot } from "../lib/types";

function activityIcon(kind: string) {
  switch (kind) {
    case "upload":
      return "upload" as const;
    case "download":
      return "download" as const;
    case "conflict":
      return "conflict" as const;
    case "error":
      return "alert" as const;
    case "account":
      return "link" as const;
    case "sync":
      return "refresh" as const;
    default:
      return "info" as const;
  }
}

export function Dashboard({
  snapshot,
  accounts,
  profiles,
  activity,
  usage,
  emails,
  onRefreshUsage,
  onSyncAll,
  onTogglePause,
  onAddAccount,
  onOpenActivity,
  onOpenFolders,
  onSyncProfile,
  onDeleteAccount,
}: {
  snapshot: Snapshot;
  accounts: Account[];
  profiles: Profile[];
  activity: ActivityEntry[];
  usage: AccountUsage[];
  emails: Record<string, string>;
  onRefreshUsage: () => void;
  onSyncAll: () => void;
  onTogglePause: () => void;
  onAddAccount: () => void;
  onOpenActivity: () => void;
  onOpenFolders: () => void;
  onSyncProfile: (id: string) => void;
  onDeleteAccount: (account: string) => Promise<void>;
}) {
  const t = useT();
  const enabled = profiles.filter((profile) => profile.enabled);
  const [removendo, setRemovendo] = useState<Account | null>(null);
  const pending = snapshot.transfers.filter((transfer) => transfer.percent < 100);
  const lastSync = profiles
    .map((profile) => profile.lastSync ?? 0)
    .reduce((left, right) => Math.max(left, right), 0);
  const percent =
    snapshot.totalBytes > 0
      ? Math.min(100, Math.round((snapshot.bytes / snapshot.totalBytes) * 100))
      : 0;

  const heroClass = snapshot.paused ? "paused" : snapshot.running ? "" : "idle";
  const title = snapshot.paused
    ? t("Sincronização pausada")
    : snapshot.running
      ? t("Sincronizando agora")
      : t("Tudo em dia");
  const subtitle = snapshot.paused
    ? t("Nada foi perdido: retome quando quiser.")
    : snapshot.running
      ? `${t(
          snapshot.jobs === 1 ? "{n} tarefa em andamento" : "{n} tarefas em andamento",
          { n: snapshot.jobs },
        )} · ${formatSpeed(snapshot.speed)}`
      : lastSync > 0
        ? t("Última verificação {tempo}", { tempo: relativeTime(lastSync) })
        : t("Adicione uma pasta para começar.");

  return (
    <div>
      <section className={`hero ${heroClass}`}>
        <div className="hero-top">
          <div className="hero-icon">
            <Icon
              name={snapshot.paused ? "pause" : snapshot.running ? "refresh" : "check"}
              size={22}
              className={snapshot.running && !snapshot.paused ? "spin" : undefined}
            />
          </div>
          <div>
            <h2>{title}</h2>
            <div className="hero-sub">{subtitle}</div>
          </div>
          <div className="hero-actions">
            {!snapshot.running && !snapshot.paused ? (
              <button className="btn light" onClick={onSyncAll} disabled={enabled.length === 0}>
                <Icon name="refresh" size={16} />
                {t("Sincronizar agora")}
              </button>
            ) : null}
            <button className="btn on-hero" onClick={onTogglePause}>
              <Icon name={snapshot.paused ? "play" : "pause"} size={15} />
              {snapshot.paused ? t("Retomar") : t("Pausar tudo")}
            </button>
          </div>
        </div>

        <div className="hero-stats">
          <div>
            <div className="hero-stat-label">{t("Velocidade")}</div>
            <div className="hero-stat-value">
              {snapshot.running ? formatSpeed(snapshot.speed) : "—"}
            </div>
          </div>
          <div>
            <div className="hero-stat-label">{t("Transferido")}</div>
            <div className="hero-stat-value">
              {snapshot.running ? formatBytes(snapshot.bytes) : "0 B"}
            </div>
          </div>
          <div>
            <div className="hero-stat-label">{t("Pastas ativas")}</div>
            <div className="hero-stat-value">
              {t("{a} de {b}", { a: enabled.length, b: profiles.length })}
            </div>
          </div>
        </div>

        {snapshot.running ? (
          <div className="hero-bar">
            <div className={`hero-track ${percent === 0 ? "indeterminate" : ""}`}>
              <span
                className={percent > 0 ? "active" : undefined}
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="hero-percent">{percent}%</span>
          </div>
        ) : null}
      </section>

      <div className="dashboard-grid">
        <div className="stack">
          <section className="card">
            <div className="card-head">
              <h2>{t("Na fila")}</h2>
              <span className="spacer" />
              {snapshot.running ? (
                <span className="muted" style={{ fontSize: 12 }}>
                  {t("{a} de {b}", {
                    a: formatBytes(snapshot.bytes),
                    b: formatBytes(snapshot.totalBytes),
                  })}
                </span>
              ) : null}
            </div>
            <div className="card-body">
              {pending.length === 0 ? (
                <div className="empty" style={{ padding: "26px 12px" }}>
                  <div className="empty-art">
                    <Icon
                      name={snapshot.running ? "refresh" : "check"}
                      size={26}
                      className={snapshot.running ? "spin" : undefined}
                    />
                  </div>
                  <h3>
                    {snapshot.running
                      ? t("Verificando alterações…")
                      : t("Nada para transferir")}
                  </h3>
                  <p>
                    {snapshot.paused
                      ? t("A sincronização está pausada.")
                      : snapshot.running
                        ? t("Comparando arquivos locais e da nuvem.")
                        : t("Todas as pastas ativas estão atualizadas.")}
                  </p>
                  {enabled.length > 0 && !snapshot.running ? (
                    <button className="btn sm ghost" onClick={onSyncAll}>
                      <Icon name="refresh" size={14} />
                      {t("Verificar novamente")}
                    </button>
                  ) : null}
                </div>
              ) : (
                pending.map((transfer) => (
                  <div className="transfer" key={transfer.name}>
                    <div className="transfer-icon active">
                      <Icon name="upload" size={16} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div className="transfer-name" title={transfer.name}>
                        {transfer.name}
                      </div>
                      <div className="transfer-meta">
                        <span>
                          {t("{a} de {b}", {
                            a: formatBytes(transfer.bytes),
                            b: formatBytes(transfer.size),
                          })}
                        </span>
                        <span>·</span>
                        <span>{formatSpeed(transfer.speed)}</span>
                        <span>·</span>
                        <span>{t("faltam {tempo}", { tempo: formatEta(transfer.eta) })}</span>
                      </div>
                      <div className="progress" style={{ marginTop: 7 }}>
                        <span className="active" style={{ width: `${Math.round(transfer.percent)}%` }} />
                      </div>
                    </div>
                    <div className="transfer-percent">{Math.round(transfer.percent)}%</div>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>{t("Atividade recente")}</h2>
              <span className="spacer" />
              <button className="link" onClick={onOpenActivity}>
                {t("Ver tudo")}
              </button>
            </div>
            <div className="card-body" style={{ paddingTop: 6 }}>
              {activity.length === 0 ? (
                <p className="muted" style={{ fontSize: 12.5, padding: "10px 0" }}>
                  {t("Nada por aqui ainda.")}
                </p>
              ) : (
                <div className="mini-activity">
                  {activity.slice(0, 4).map((entry) => (
                    <div className="mini-row" key={entry.id}>
                      <div className={`feed-icon ${entry.kind}`} style={{ width: 28, height: 28 }}>
                        <Icon name={activityIcon(entry.kind)} size={14} />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div className="mini-title">{t(entry.title)}</div>
                        <div className="mini-detail">{t(entry.detail)}</div>
                        {entry.files && entry.files.length > 0 ? (
                          <div className="mini-files">{resumoTexto(entry.files)}</div>
                        ) : null}
                      </div>
                      <div className="mini-time">{relativeTime(entry.at)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <div className="card-head">
              <h2>{t("Contas")}</h2>
              <span className="spacer" />
              <button className="link" onClick={onAddAccount}>
                {t("Adicionar")}
              </button>
            </div>
            <div className="card-body" style={{ paddingTop: 8 }}>
              <div className="accounts">
                {accounts.map((account) => {
                  const linked = profiles.filter((profile) => profile.account === account.name);
                  const failing = linked.some((profile) => profile.lastError);
                  return (
                    <div className="account" key={account.name}>
                      <div className={`provider ${account.provider}`}>
                        <Icon
                          name={
                            account.provider === "drive" ||
                            account.provider === "onedrive" ||
                            account.provider === "dropbox" ||
                            account.provider === "nextcloud"
                              ? account.provider
                              : "cloud"
                          }
                          size={18}
                        />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div className="account-name">{account.name}</div>
                        <div className="account-meta">
                          {emails[account.name] ?? account.label} ·{" "}
                          {linked.length === 1
                            ? t("1 pasta")
                            : t("{n} pastas", { n: linked.length })}
                        </div>
                      </div>
                      <div className="account-status">
                        <span className={`dot ${failing ? "danger" : linked.length ? "ok" : ""}`} />
                        {failing
                          ? t("atenção")
                          : linked.length
                            ? t("conectada")
                            : t("sem pasta")}
                      </div>
                      <button
                        className="tiny-btn account-remove"
                        title={t("Remover conta")}
                        aria-label={t("Remover a conta {nome}", { nome: account.name })}
                        onClick={() => setRemovendo(account)}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    </div>
                  );
                })}
                {accounts.length === 0 ? (
                  <div className="empty" style={{ padding: "20px 8px" }}>
                    <div className="empty-art">
                      <Icon name="cloud" size={24} />
                    </div>
                    <h3>{t("Nenhuma conta ainda")}</h3>
                    <p>{t("Conecte Google Drive, OneDrive, Dropbox ou Nextcloud para começar.")}</p>
                    <button className="btn sm primary" onClick={onAddAccount}>
                      <Icon name="plus" size={14} />
                      {t("Conectar conta")}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>{t("Armazenamento")}</h2>
            </div>
            <div className="card-body" style={{ paddingTop: 8 }}>
              {usage.length === 0 ? (
                <p className="muted" style={{ fontSize: 12.5, padding: "6px 0" }}>
                  {accounts.length === 0
                    ? t("Conecte uma conta para ver a cota.")
                    : t("Lendo a cota…")}
                </p>
              ) : (
                usage.map((item) => {
                  const percent =
                    item.total && item.used
                      ? Math.min(100, Math.round((item.used / item.total) * 100))
                      : 0;
                  const temNumeros = item.total !== null && item.used !== null;
                  return (
                    <div className="quota" key={item.account}>
                      <div className="quota-head">
                        <span className="quota-name">{item.account}</span>
                        <span className="quota-value">
                          {temNumeros
                            ? t("{a} de {b}", {
                                a: formatBytes(item.used!),
                                b: formatBytes(item.total!),
                              })
                            : item.error
                              ? t("não consegui ler agora")
                              : t("lendo…")}
                        </span>
                      </div>
                      <div className="progress" style={{ marginTop: 6 }}>
                        <span style={{ width: `${percent}%` }} />
                      </div>
                      <div className="quota-foot">
                        <span>{emails[item.account] ?? item.label}</span>
                        {item.error ? (
                          item.stale ? (
                            // A leitura falhou, mas o número anterior continua valendo.
                            <span className="badge warn" title={item.error}>
                              {t("desatualizada")}
                            </span>
                          ) : (
                            <button className="link" title={item.error} onClick={onRefreshUsage}>
                              {t("tentar de novo")}
                            </button>
                          )
                        ) : (
                          <span>{t("{n}% usado", { n: percent })}</span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>{t("Pastas")}</h2>
              <span className="spacer" />
              <button className="link" onClick={onOpenFolders}>
                {t("Gerenciar")}
              </button>
            </div>
            <div className="card-body" style={{ paddingTop: 6 }}>
              {enabled.length === 0 ? (
                <p className="muted" style={{ fontSize: 12.5, padding: "8px 0" }}>
                  {t("Nenhuma pasta ativa.")}
                </p>
              ) : (
                enabled.slice(0, 5).map((profile) => (
                  <div className="mini-row" key={profile.id}>
                    <div className="file-ico dir" style={{ width: 28, height: 28 }}>
                      <Icon name="folder" size={14} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div className="mini-title" title={`${profile.account}:${profile.remotePath}`}>
                        {profile.remotePath || profile.account}
                      </div>
                      <div className="mini-detail">{profile.localPath}</div>
                    </div>
                    <div
                      style={{
                        marginLeft: "auto",
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        flex: "none",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {profile.lastError ? (
                        <span className="badge danger">{t("erro")}</span>
                      ) : profile.resyncNeeded ? (
                        <span className="badge warn">{t("ressincronizar")}</span>
                      ) : (
                        <span className="badge ok">{t("em dia")}</span>
                      )}
                      <button
                        className="tiny-btn"
                        onClick={() => onSyncProfile(profile.id)}
                        title={t("Sincronizar esta pasta")}
                        aria-label={t("Sincronizar {pasta}", {
                          pasta: profile.remotePath || profile.account,
                        })}
                      >
                        <Icon name="refresh" size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </div>

      {removendo ? (
        <Modal
          title={t("Remover {nome}?", { nome: removendo.name })}
          onClose={() => setRemovendo(null)}
          footer={
            removendo &&
            profiles.some((profile) => profile.account === removendo.name) ? (
              <button
                className="btn primary"
                onClick={() => {
                  setRemovendo(null);
                  onOpenFolders();
                }}
              >
                {t("Abrir Pastas")}
              </button>
            ) : (
              <>
                <button className="btn ghost" onClick={() => setRemovendo(null)}>
                  {t("Cancelar")}
                </button>
                <button
                  className="btn danger"
                  onClick={() => {
                    void onDeleteAccount(removendo.name);
                    setRemovendo(null);
                  }}
                >
                  {t("Remover conta")}
                </button>
              </>
            )
          }
        >
          <p style={{ fontSize: 13, color: "var(--text-soft)" }}>
            {t(
              "O BrisaSync apaga as credenciais desta conta do rclone neste computador. Nada é apagado na nuvem nem no disco.",
            )}
          </p>
          {profiles.some((profile) => profile.account === removendo.name) ? (
            <p style={{ fontSize: 12.5, color: "var(--warn)", marginTop: 10 }}>
              {t(
                "Esta conta ainda tem pasta configurada. Remova a pasta antes para não deixar um par de sincronização apontando para uma conta que não existe.",
              )}
            </p>
          ) : (
            <p style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 10 }}>
              {t(
                "Para voltar depois, é só conectar de novo (o navegador abre para a autorização).",
              )}
            </p>
          )}
        </Modal>
      ) : null}
    </div>
  );
}
