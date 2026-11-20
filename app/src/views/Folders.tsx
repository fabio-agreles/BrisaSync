import { useEffect, useState } from "react";
import { Icon } from "../components/Icons";
import { Modal } from "../components/Modal";
import { api, errorMessage } from "../lib/bridge";
import { joinPath, relativeTime } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Account, Profile, RemoteEntry } from "../lib/types";

/// Erros do rclone são longos ("bisync aborted", "a pasta na nuvem está
/// vazia…"). O cartão mostra o começo; o texto inteiro — e a dica de
/// ressincronizar — ficam no tooltip.
function resumoDoErro(texto: string): string {
  const limpo = texto.replace(/\s+/g, " ").trim();
  return limpo.length > 46 ? `${limpo.slice(0, 44).trimEnd()}…` : limpo;
}

export function Folders({
  profiles,
  accounts,
  onAddFolder,
  onUpdate,
  onDelete,
  onSync,
  notify,
}: {
  profiles: Profile[];
  accounts: Account[];
  onAddFolder: () => void;
  onUpdate: (profile: Profile) => void;
  onDelete: (id: string) => void;
  onSync: (id: string, resync?: boolean) => void;
  notify: (message: string, kind?: "info" | "ok" | "error") => void;
}) {
  const t = useT();
  const [confirming, setConfirming] = useState<Profile | null>(null);
  const [selecting, setSelecting] = useState<Profile | null>(null);

  return (
    <div>
      <div className="toolbar">
        <div>
          <strong style={{ fontSize: 13.5 }}>{t("Pastas sincronizadas")}</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            {t("Cada pasta liga uma pasta da nuvem a uma pasta local.")}
          </div>
        </div>
        <span style={{ flex: 1 }} />
        <button className="btn primary" onClick={onAddFolder} disabled={accounts.length === 0}>
          <Icon name="plus" size={16} />
          {t("Adicionar pasta")}
        </button>
      </div>

      {accounts.length === 0 ? (
        <div className="banner info" style={{ marginBottom: 14 }}>
          <Icon name="info" size={16} />
          {t("Conecte uma conta antes de escolher pastas.")}
        </div>
      ) : null}

      <section className="card" style={{ overflow: "hidden" }}>
        {profiles.length === 0 ? (
          <div className="empty">
            <div className="empty-art">
              <Icon name="layers" size={28} />
            </div>
            <h3>{t("Nenhuma pasta ainda")}</h3>
            <p>
              {t(
                "Escolha uma pasta na nuvem e uma pasta local. O BrisaSync mantém as duas iguais, nos dois sentidos.",
              )}
            </p>
            <button className="btn primary" onClick={onAddFolder} disabled={accounts.length === 0}>
              <Icon name="plus" size={16} />
              {t("Adicionar pasta")}
            </button>
          </div>
        ) : (
          profiles.map((profile) => {
            const provider =
              accounts.find((account) => account.name === profile.account)?.provider ?? "other";
            return (
            <div className="folder-row" key={profile.id}>
              <div className="folder-name">
                <div
                  className={`provider ${provider}`}
                  style={{ width: 34, height: 34, borderRadius: 10 }}
                >
                  <Icon
                    name={
                      provider === "drive" ||
                      provider === "onedrive" ||
                      provider === "dropbox" ||
                      provider === "nextcloud"
                        ? provider
                        : "cloud"
                    }
                    size={17}
                  />
                </div>
                <div style={{ minWidth: 0 }}>
                  <strong title={`${profile.account}:${profile.remotePath}`}>
                    {profile.remotePath || t("Raiz da conta")}
                  </strong>
                  <div className="folder-path" title={profile.localPath}>
                    {profile.account} → {profile.localPath}
                  </div>
                </div>
              </div>

              <div className="folder-state">
                {profile.lastError ? (
                  // O erro é um botão: é por ele que se pede a ressincronização
                  // (aceitar o estado atual das duas pastas). Sem isso, um aviso
                  // como "a pasta na nuvem está vazia" não teria saída na tela.
                  <button
                    className="badge danger"
                    style={{
                      border: "none",
                      cursor: "pointer",
                      fontFamily: "inherit",
                      fontSize: 11,
                      fontWeight: 600,
                      maxWidth: "100%",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={`${profile.lastError}\n\n${t("Clique para Ressincronizar: aceita o estado atual das duas pastas e refaz a base de comparação.")}`}
                    aria-label={t("{erro} — Ressincronizar {pasta}", {
                      erro: profile.lastError,
                      pasta: profile.remotePath || profile.account,
                    })}
                    onClick={() => onSync(profile.id, true)}
                  >
                    <Icon name="alert" size={12} />
                    {resumoDoErro(profile.lastError)}
                  </button>
                ) : !profile.enabled ? (
                  <span className="badge muted">{t("desativada")}</span>
                ) : profile.resyncNeeded ? (
                  <span className="badge warn">{t("precisa ressincronizar")}</span>
                ) : (
                  <span className="badge ok">
                    <Icon name="check" size={12} />
                    {t("em dia · {tempo}", { tempo: relativeTime(profile.lastSync) })}
                  </span>
                )}
                {(profile.excludedFolders?.length ?? 0) > 0 ? (
                  <span className="badge muted" style={{ marginLeft: 6 }}>
                    {t(
                      profile.excludedFolders!.length === 1
                        ? "{n} subpasta ignorada"
                        : "{n} subpastas ignoradas",
                      { n: profile.excludedFolders!.length },
                    )}
                  </span>
                ) : null}
              </div>

              <div className="folder-actions">
                <button
                  className="tiny-btn"
                  title={t("Sincronização seletiva")}
                  aria-label={t("Escolher subpastas")}
                  onClick={() => setSelecting(profile)}
                >
                  <Icon name="layers" size={15} />
                </button>
                <button
                  className="tiny-btn"
                  title={t("Abrir pasta local")}
                  aria-label={t("Abrir {caminho}", { caminho: profile.localPath })}
                  onClick={() => {
                    void api
                      .revealPath(profile.localPath)
                      .catch((cause) => notify(errorMessage(cause), "error"));
                  }}
                >
                  <Icon name="folder-open" size={15} />
                </button>
                <button
                  className="tiny-btn"
                  title={t("Sincronizar agora")}
                  aria-label={t("Sincronizar {pasta}", {
                    pasta: profile.remotePath || profile.account,
                  })}
                  disabled={!profile.enabled}
                  onClick={() => onSync(profile.id, profile.resyncNeeded)}
                >
                  <Icon name="refresh" size={15} />
                </button>
                <button
                  className={`switch ${profile.enabled ? "on" : ""}`}
                  role="switch"
                  aria-checked={profile.enabled}
                  title={profile.enabled ? t("Desativar") : t("Ativar")}
                  aria-label={profile.enabled ? t("Desativar pasta") : t("Ativar pasta")}
                  onClick={() => onUpdate({ ...profile, enabled: !profile.enabled })}
                />
                <button
                  className="tiny-btn"
                  title={t("Remover")}
                  aria-label={t("Remover {pasta}", {
                    pasta: profile.remotePath || profile.account,
                  })}
                  onClick={() => setConfirming(profile)}
                >
                  <Icon name="trash" size={15} />
                </button>
              </div>
            </div>
            );
          })
        )}
      </section>

      <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
        {t("O modo")} <strong>bisync</strong>{" "}
        {t(
          "compara os dois lados e propaga as mudanças. Ao alterar caminhos, a próxima execução faz uma ressincronização completa.",
        )}
      </p>

      {confirming ? (
        <Modal
          title={t("Remover pasta?")}
          onClose={() => setConfirming(null)}
          footer={
            <>
              <button className="btn ghost" onClick={() => setConfirming(null)}>
                {t("Cancelar")}
              </button>
              <button
                className="btn danger"
                onClick={() => {
                  onDelete(confirming.id);
                  setConfirming(null);
                }}
              >
                {t("Remover")}
              </button>
            </>
          }
        >
          <p style={{ fontSize: 13, color: "var(--text-soft)" }}>
            {t("A pasta local")} <strong>{confirming.localPath}</strong>{" "}
            {t(
              "não será apagada nem enviada. Apenas o par de sincronização sai do BrisaSync.",
            )}
          </p>
        </Modal>
      ) : null}

      {selecting ? (
        <SelectiveSyncModal
          profile={selecting}
          onClose={() => setSelecting(null)}
          onSave={(excludedFolders) => {
            onUpdate({ ...selecting, excludedFolders });
            notify(t("Seleção salva. A próxima sincronização aplicará os filtros."), "ok");
            setSelecting(null);
          }}
        />
      ) : null}
    </div>
  );
}

function SelectiveSyncModal({
  profile,
  onClose,
  onSave,
}: {
  profile: Profile;
  onClose: () => void;
  onSave: (excludedFolders: string[]) => void;
}) {
  const t = useT();
  const [subPath, setSubPath] = useState("");
  const [dirs, setDirs] = useState<RemoteEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [excluded, setExcluded] = useState<Set<string>>(
    () => new Set(profile.excludedFolders ?? []),
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    const fullPath = joinPath(profile.remotePath, subPath);
    void api
      .listRemote(profile.account, fullPath)
      .then((entries) => {
        if (!active) return;
        setDirs(entries.filter((entry) => entry.isDir));
      })
      .catch((cause) => {
        if (!active) return;
        setDirs([]);
        setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [profile.account, profile.remotePath, subPath]);

  const segments = subPath.split("/").filter(Boolean);

  const isExcluded = (relPath: string) => {
    if (excluded.has(relPath)) return true;
    const parts = relPath.split("/");
    for (let i = 1; i < parts.length; i += 1) {
      if (excluded.has(parts.slice(0, i).join("/"))) return true;
    }
    return false;
  };

  const toggle = (relPath: string) => {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(relPath)) {
        next.delete(relPath);
      } else {
        next.add(relPath);
      }
      return next;
    });
  };

  return (
    <Modal
      title={t("Sincronização seletiva")}
      onClose={onClose}
      footer={
        <>
          <button className="btn ghost" onClick={onClose}>
            {t("Cancelar")}
          </button>
          <button
            className="btn primary"
            onClick={() => onSave(Array.from(excluded).sort())}
          >
            {t("Salvar seleção")}
          </button>
        </>
      }
    >
      <p className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
        {t("Desmarque as subpastas que não devem ser baixadas para este computador.")}
      </p>

      <div className="breadcrumb" style={{ marginBottom: 10 }}>
        <button
          onClick={() => setSubPath("")}
          className={segments.length === 0 ? "current" : undefined}
        >
          {profile.remotePath || t("Raiz da pasta")}
        </button>
        {segments.map((segment, index) => {
          const target = segments.slice(0, index + 1).join("/");
          const last = index === segments.length - 1;
          return (
            <span key={target} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <Icon name="chevron-right" size={13} />
              <button
                onClick={() => setSubPath(target)}
                className={last ? "current" : undefined}
              >
                {segment}
              </button>
            </span>
          );
        })}
      </div>

      {error ? (
        <div className="banner danger" style={{ marginBottom: 10 }}>
          <Icon name="alert" size={15} />
          <span>{error}</span>
        </div>
      ) : null}

      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: 12,
          maxHeight: 280,
          overflowY: "auto",
        }}
      >
        {loading ? (
          <div className="empty" style={{ padding: "24px 12px" }}>
            <Icon name="refresh" size={20} className="spin" />
          </div>
        ) : dirs.length === 0 ? (
          <div className="empty" style={{ padding: "24px 12px" }}>
            <p className="muted" style={{ fontSize: 12.5 }}>
              {t("Nenhuma subpasta encontrada aqui.")}
            </p>
          </div>
        ) : (
          dirs.map((dir) => {
            const relPath = joinPath(subPath, dir.name);
            const checked = !isExcluded(relPath);
            return (
              <div
                key={dir.path}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "9px 12px",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(relPath)}
                  aria-label={dir.name}
                />
                <Icon name="folder" size={16} />
                <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{dir.name}</span>
                <button
                  className="tiny-btn"
                  disabled={!checked}
                  onClick={() => setSubPath(relPath)}
                  title={dir.name}
                >
                  <Icon name="chevron-right" size={14} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </Modal>
  );
}
