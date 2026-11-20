import { Icon } from "./Icons";
import type { Snapshot } from "../lib/types";
import { useT } from "../lib/i18n";

type Tr = (texto: string, valores?: Record<string, string | number>) => string;

function statusOf(snapshot: Snapshot, tr: Tr) {
  if (snapshot.paused) return { tone: "warn", label: tr("Pausado") };
  if (snapshot.running) {
    const count = snapshot.jobs;
    return {
      tone: "busy",
      label:
        count === 1
          ? tr("Sincronizando 1 tarefa")
          : tr("Sincronizando {n} tarefas", { n: count }),
    };
  }
  return { tone: "ok", label: tr("Tudo em dia") };
}

export function TopBar({
  title,
  subtitle,
  snapshot,
  theme,
  onToggleTheme,
  onOpenPalette,
  onStatusClick,
}: {
  title: string;
  subtitle: string;
  snapshot: Snapshot;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onOpenPalette: () => void;
  onStatusClick: () => void;
}) {
  const t = useT();
  const status = statusOf(snapshot, t);

  return (
    <header className="topbar">
      <div className="topbar-titles">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>

      <div className="topbar-actions">
        <button className="pill" onClick={onStatusClick} title={t("Abrir visão geral")}>
          <span className={`dot ${status.tone}`} />
          {status.label}
        </button>

        <button className="search-btn" onClick={onOpenPalette} aria-label={t("Abrir busca de ações")}>
          <Icon name="search" size={15} />
          <span>{t("Buscar")}</span>
          <span className="kbd">Ctrl K</span>
        </button>

        <button
          className="icon-btn"
          onClick={onToggleTheme}
          aria-label={theme === "light" ? t("Ativar tema escuro") : t("Ativar tema claro")}
          title={theme === "light" ? t("Tema escuro") : t("Tema claro")}
        >
          <Icon name={theme === "light" ? "moon" : "sun"} size={18} />
        </button>

      </div>
    </header>
  );
}
