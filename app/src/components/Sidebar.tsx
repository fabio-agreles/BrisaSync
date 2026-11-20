import { Icon, type IconName } from "./Icons";
import type { EngineStatus, ViewId } from "../lib/types";
import { isDesktop } from "../lib/bridge";
import { NOME } from "../lib/marca";
import { useT } from "../lib/i18n";
import logo from "../assets/logo.png";

type NavItem = {
  id: ViewId;
  label: string; // chave em português; traduzida na hora de desenhar
  icon: IconName;
  shortcut: string;
};

const ITEMS: NavItem[] = [
  { id: "dashboard", label: "Visão geral", icon: "dashboard", shortcut: "1" },
  { id: "files", label: "Arquivos", icon: "folder", shortcut: "2" },
  { id: "folders", label: "Pastas", icon: "layers", shortcut: "3" },
  { id: "activity", label: "Atividade", icon: "activity", shortcut: "4" },
  { id: "conflicts", label: "Conflitos", icon: "conflict", shortcut: "5" },
  { id: "settings", label: "Ajustes", icon: "settings", shortcut: "6" },
];

export function Sidebar({
  view,
  onNavigate,
  folderCount,
  conflictCount,
  engine,
}: {
  view: ViewId;
  onNavigate: (view: ViewId) => void;
  folderCount: number;
  conflictCount: number;
  engine: EngineStatus | null;
}) {
  const t = useT();

  return (
    <aside className="sidebar">
      <div className="brand">
        <img className="brand-mark" src={logo} alt="" width={36} height={36} />
        <div className="brand-text">
          <div className="brand-name">{NOME}</div>
          <div className="brand-sub">{t("sincronização simples")}</div>
        </div>
      </div>

      <div className="nav-label">{t("Navegação")}</div>
      {ITEMS.map((item) => (
        <button
          key={item.id}
          className={`nav-item ${view === item.id ? "active" : ""}`}
          onClick={() => onNavigate(item.id)}
          title={`${t(item.label)} (${item.shortcut})`}
          aria-current={view === item.id ? "page" : undefined}
        >
          <Icon name={item.icon} size={18} />
          <span>{t(item.label)}</span>
          {item.id === "folders" && folderCount > 0 ? (
            <span className="nav-count">{folderCount}</span>
          ) : null}
          {item.id === "conflicts" && conflictCount > 0 ? (
            <span className="nav-count">{conflictCount}</span>
          ) : null}
        </button>
      ))}

      <div className="sidebar-foot">
        {isDesktop ? (
          <>
            <div className="sidebar-card">
              <strong>
                {engine?.available ? t("rclone conectado") : t("Motor indisponível")}
              </strong>
              {engine?.available
                ? (engine.version ?? t("versão desconhecida"))
                : t("Instale o rclone para sincronizar de verdade.")}
            </div>
            <div className="sidebar-card">
              <strong>{t("Sincroniza na bandeja")}</strong>
              {t("Fechar a janela não interrompe as pastas.")}
            </div>
          </>
        ) : (
          <div className="sidebar-card">
            <strong>{t("Modo demonstração")}</strong>
            {t("Dados simulados, sem rclone nem contas reais.")}
          </div>
        )}
      </div>
    </aside>
  );
}
