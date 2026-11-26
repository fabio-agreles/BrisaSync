import { useT } from "../lib/i18n";
import { Icon } from "./Icons";
import { Modal } from "./Modal";

export function OnboardingModal({
  hasAccount,
  onConnectAccount,
  onAddFolder,
  onDismiss,
}: {
  hasAccount: boolean;
  onConnectAccount: () => void;
  onAddFolder: () => void;
  onDismiss: () => void;
}) {
  const t = useT();

  return (
    <Modal
      title={hasAccount ? t("Quase pronto para sincronizar") : t("Bem-vindo ao BrisaSync")}
      onClose={onDismiss}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onDismiss}>
            {t("Configurar depois")}
          </button>
          {hasAccount ? (
            <button type="button" className="btn btn-primary" onClick={onAddFolder}>
              <Icon name="folder" size={15} />
              {t("Escolher primeira pasta")}
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={onConnectAccount}>
              <Icon name="link" size={15} />
              {t("Conectar primeira conta")}
            </button>
          )}
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.55 }}>
          {hasAccount
            ? t("Sua conta já está conectada. Agora escolha uma pasta deste computador para manter em sincronização bidirecional com a nuvem.")
            : t("Mantenha suas pastas em sincronização bidirecional com Google Drive, OneDrive, Dropbox ou Nextcloud em dois passos simples.")}
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "12px 14px",
              borderRadius: "var(--radius-sm)",
              background: hasAccount ? "var(--ok-soft)" : "var(--accent-soft)",
              border: `1px solid ${hasAccount ? "var(--ok)" : "var(--accent)"}`,
            }}
          >
            <span
              style={{
                width: 26,
                height: 26,
                borderRadius: 999,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 700,
                fontSize: 13,
                background: hasAccount ? "var(--ok)" : "var(--accent)",
                color: "#fff",
                flexShrink: 0,
              }}
            >
              {hasAccount ? "✓" : "1"}
            </span>
            <div>
              <div style={{ fontWeight: 600 }}>{t("Conectar uma conta na nuvem")}</div>
              <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
                {t("Google Drive, OneDrive, Dropbox ou Nextcloud via login direto.")}
              </div>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "12px 14px",
              borderRadius: "var(--radius-sm)",
              background: hasAccount ? "var(--accent-soft)" : "var(--surface-2)",
              border: `1px solid ${hasAccount ? "var(--accent)" : "var(--border)"}`,
              opacity: hasAccount ? 1 : 0.75,
            }}
          >
            <span
              style={{
                width: 26,
                height: 26,
                borderRadius: 999,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 700,
                fontSize: 13,
                background: hasAccount ? "var(--accent)" : "var(--surface-3)",
                color: hasAccount ? "#fff" : "var(--muted)",
                flexShrink: 0,
              }}
            >
              2
            </span>
            <div>
              <div style={{ fontWeight: 600 }}>{t("Escolher a primeira pasta")}</div>
              <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
                {t("Defina a pasta local e a pasta remota que ficarão iguais nos dois lados.")}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
