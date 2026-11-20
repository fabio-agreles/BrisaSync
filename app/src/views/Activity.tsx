import { useEffect, useMemo, useState } from "react";
import { Icon } from "../components/Icons";
import { Modal } from "../components/Modal";
import { clock, dayLabel, relativeTime } from "../lib/format";
import { grupos, resumo } from "../lib/files";
import { locale, useT } from "../lib/i18n";
import type { ActivityEntry } from "../lib/types";

const FILTERS = [
  { id: "all", label: "Tudo" },
  { id: "upload", label: "Envios" },
  { id: "download", label: "Downloads" },
  { id: "conflict", label: "Conflitos" },
  { id: "error", label: "Erros" },
]; // rótulos em português; traduzidos na hora de desenhar

/// Quantos nomes cabem antes do “+N”.
const VISIVEIS = 8;

function iconFor(kind: string) {
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

export function Activity({
  entries,
  onClear,
}: {
  entries: ActivityEntry[];
  /// Apaga o histórico de vez (memória + arquivo em disco).
  onClear: () => Promise<void>;
}) {
  const t = useT();
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [limpando, setLimpando] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setExpanded(null);
  }, [filter]);

  const filtered = useMemo(
    () => (filter === "all" ? entries : entries.filter((entry) => entry.kind === filter)),
    [entries, filter],
  );

  const groups = useMemo(() => {
    const buckets: { label: string; items: ActivityEntry[] }[] = [];
    for (const entry of filtered) {
      const label = dayLabel(entry.at);
      let bucket = buckets.find((item) => item.label === label);
      if (!bucket) {
        bucket = { label, items: [] };
        buckets.push(bucket);
      }
      bucket.items.push(entry);
    }
    return buckets;
  }, [filtered]);

  return (
    <div>
      <div className="chips">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            className={`chip ${filter === item.id ? "active" : ""}`}
            onClick={() => setFilter(item.id)}
          >
            {t(item.label)}
            {item.id !== "all" ? (
              <span style={{ marginLeft: 6, opacity: 0.7 }}>
                {entries.filter((entry) => entry.kind === item.id).length}
              </span>
            ) : null}
          </button>
        ))}
        {entries.length > 0 ? (
          <button className="chip clear" onClick={() => setLimpando(true)} title={t("Apagar todo o histórico")}>
            <Icon name="trash" size={13} />
            {t("Limpar")}
          </button>
        ) : null}
      </div>

      {filtered.length === 0 ? (
        <section className="card">
          <div className="empty">
            <div className="empty-art">
              <Icon name="activity" size={28} />
            </div>
            <h3>{t("Nada registrado")}</h3>
            <p>{t("As sincronizações, conflitos e erros aparecem aqui em ordem.")}</p>
          </div>
        </section>
      ) : (
        groups.map((group) => (
          <div key={group.label}>
            <div className="day-label">{group.label}</div>
            <section className="card" style={{ overflow: "hidden" }}>
              {group.items.map((entry) => {
                const files = entry.files ?? [];
                const aberto = expanded === entry.id;
                return (
                  <button
                    key={entry.id}
                    className={`feed-item ${aberto ? "open" : ""}`}
                    onClick={() => setExpanded(aberto ? null : entry.id)}
                    aria-expanded={aberto}
                  >
                    <span className={`feed-icon ${entry.kind}`}>
                      <Icon name={iconFor(entry.kind)} size={16} />
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <span className="feed-title" style={{ display: "block" }}>
                        {t(entry.title)}
                      </span>
                      <span className="feed-detail" style={{ display: "block" }}>
                        {t(entry.detail)}
                      </span>
                      {files.length > 0 ? (
                        <span className="file-summary">
                          {resumo(files).map((item) => (
                            <span key={item.action} className={`file-tag ${item.action}`}>
                              {item.quantos} {t(item.quantos === 1 ? item.um : item.varios)}
                            </span>
                          ))}
                          <span className="file-hint">{aberto ? t("ocultar") : t("ver arquivos")}</span>
                        </span>
                      ) : null}
                    </span>
                    <span className="feed-time" title={new Date(entry.at).toLocaleString(locale())}>
                      {clock(entry.at)}
                    </span>
                    {aberto ? (
                      <span className="feed-expanded">
                        <strong>{relativeTime(entry.at)}</strong> ·{" "}
                        {new Date(entry.at).toLocaleString(locale())}
                        <br />
                        {t(entry.detail)}
                        {entry.profile ? (
                          <>
                            <br />
                            {t("Pasta:")} <span className="mono">{entry.profile}</span>
                          </>
                        ) : null}
                        {files.length > 0 ? (
                          <span className="file-groups">
                            {grupos(files).map((grupo) => (
                              <span className="file-group" key={grupo.action}>
                                <span className="file-group-title">
                                  <span className={`file-dot ${grupo.action}`} />
                                  {t(grupo.itens.length === 1 ? grupo.um : grupo.varios)}
                                  <em>{grupo.itens.length}</em>
                                </span>
                                <span className="file-names">
                                  {grupo.itens.slice(0, VISIVEIS).map((file) => (
                                    <span className="file-name mono" key={file.name} title={file.name}>
                                      {file.name}
                                    </span>
                                  ))}
                                  {grupo.itens.length > VISIVEIS ? (
                                    <span className="file-more">
                                      +{grupo.itens.length - VISIVEIS}
                                    </span>
                                  ) : null}
                                </span>
                              </span>
                            ))}
                          </span>
                        ) : null}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </section>
          </div>
        ))
      )}

      {limpando ? (
        <Modal
          title={t("Limpar a atividade?")}
          onClose={() => setLimpando(false)}
          footer={
            <>
              <button className="btn ghost" onClick={() => setLimpando(false)} disabled={busy}>
                {t("Cancelar")}
              </button>
              <button
                className="btn danger"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await onClear();
                    setExpanded(null);
                    setLimpando(false);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? t("Limpando…") : t("Limpar tudo")}
              </button>
            </>
          }
        >
          <p style={{ fontSize: 13, color: "var(--text-soft)" }}>
            {t(
              "O histórico de envios, downloads, conflitos e erros é apagado deste computador. Os arquivos não são tocados — nem aqui, nem na nuvem.",
            )}
          </p>
          <p style={{ fontSize: 12.5, color: "var(--muted)" }}>
            {entries.length === 1
              ? t("São 1 registro. As próximas sincronizações voltam a aparecer normalmente.")
              : t(
                  "São {n} registros. As próximas sincronizações voltam a aparecer normalmente.",
                  { n: entries.length },
                )}
          </p>
        </Modal>
      ) : null}
    </div>
  );
}
