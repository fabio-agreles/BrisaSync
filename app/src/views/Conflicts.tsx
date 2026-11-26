import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Icon } from "../components/Icons";
import { Modal } from "../components/Modal";
import { api, errorMessage, isDesktop } from "../lib/bridge";
import { formatBytes, relativeTime } from "../lib/format";
import { useT } from "../lib/i18n";
import type { Conflict, TrashItem } from "../lib/types";

type Resolution = "remote" | "local" | "both";

// Rótulos em português (chaves do dicionário); traduzidos na hora de desenhar.
const RESOLUTIONS: Record<
  Resolution,
  { label: string; title: string; description: string }
> = {
  remote: {
    label: "Manter da nuvem",
    title: "Manter a versão da nuvem?",
    description:
      "A cópia deste computador vai para a pasta “conflitos-resolvidos” da configuração do BrisaSync. Nada é apagado, e a versão da nuvem volta ao nome original.",
  },
  local: {
    label: "Manter a minha",
    title: "Manter a versão deste computador?",
    description:
      "A cópia da nuvem vai para a pasta “conflitos-resolvidos” da configuração do BrisaSync. Nada é apagado, e a versão local volta ao nome original.",
  },
  both: {
    label: "Manter as duas",
    title: "Manter as duas versões?",
    description:
      "As duas cópias continuam na pasta, renomeadas com “(nuvem)” e “(local)”. O próximo bisync envia o resultado para a nuvem.",
  },
};

export function Conflicts({
  notify,
  onCount,
}: {
  notify: (message: string, kind?: "info" | "ok" | "error") => void;
  // Mantém o contador da barra lateral em dia: abrir a aba, verificar de novo e
  // resolver mexem na mesma lista.
  onCount?: (total: number) => void;
}) {
  const t = useT();
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ conflict: Conflict; action: Resolution } | null>(null);
  const [busy, setBusy] = useState(false);
  const [trash, setTrash] = useState<TrashItem[]>([]);

  const loadTrash = useCallback(async () => {
    try {
      setTrash(await api.listTrash());
    } catch {
      setTrash([]);
    }
  }, []);

  useEffect(() => {
    void loadTrash();
  }, [loadTrash]);

  const restoreItem = useCallback(
    async (item: TrashItem) => {
      let dest = "/tmp/demonstracao";
      if (isDesktop) {
        const picked = await open({
          directory: true,
          title: t("Escolha a pasta para restaurar"),
        });
        if (typeof picked !== "string") return;
        dest = picked;
      }
      try {
        const restored = await api.restoreTrashItem(item.id, dest);
        notify(t("Restaurado para {caminho}", { caminho: restored }), "ok");
        await loadTrash();
      } catch (cause) {
        notify(errorMessage(cause), "error");
      }
    },
    [loadTrash, notify, t],
  );

  const clearTrash = useCallback(async () => {
    try {
      await api.emptyTrash();
      setTrash([]);
      notify(t("Lixeira esvaziada."), "ok");
    } catch (cause) {
      notify(errorMessage(cause), "error");
    }
  }, [notify, t]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const lista = await api.scanConflicts();
      setConflicts(lista);
      onCount?.(lista.length);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, [onCount]);

  useEffect(() => {
    void load();
  }, [load]);

  const resolve = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const remaining = await api.resolveConflict(pending.action, pending.conflict);
      setConflicts(remaining);
      onCount?.(remaining.length);
      notify(t("Conflito resolvido: {arquivo}", { arquivo: pending.conflict.baseName }), "ok");
      setPending(null);
    } catch (cause) {
      notify(errorMessage(cause), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="toolbar">
        <div>
          <strong style={{ fontSize: 13.5 }}>{t("Conflitos de sincronização")}</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            {t("O bisync guarda as duas versões com os sufixos")}{" "}
            <span className="mono">..path1</span> {t("e")}{" "}
            <span className="mono">..path2</span>.
          </div>
        </div>
        <span style={{ flex: 1 }} />
        <button className="btn ghost" onClick={() => void load()}>
          <Icon name="refresh" size={16} className={loading ? "spin" : undefined} />
          {t("Verificar de novo")}
        </button>
      </div>

      {error ? (
        <div className="banner danger" style={{ marginBottom: 14 }}>
          <Icon name="alert" size={16} />
          {error}
        </div>
      ) : null}

      {conflicts.length === 0 ? (
        <section className="card">
          <div className="empty">
            <div className="empty-art">
              <Icon name="shield" size={28} />
            </div>
            <h3>{loading ? t("Verificando…") : t("Nenhum conflito")}</h3>
            <p>
              {t(
                "Quando o mesmo arquivo muda dos dois lados, o BrisaSync avisa aqui em vez de escolher sozinho.",
              )}
            </p>
            {!loading ? (
              <button className="btn ghost sm" onClick={() => void load()}>
                <Icon name="refresh" size={14} />
                {t("Verificar novamente")}
              </button>
            ) : null}
          </div>
        </section>
      ) : (
        conflicts.map((conflict) => (
          <article className="conflict-card" key={conflict.id}>
            <div className="conflict-side">
              <div className="conflict-tag">
                <Icon name="cloud" size={13} />
                {t("Na nuvem")}
              </div>
              <div className="conflict-name">{conflict.baseName}</div>
              <div className="conflict-meta">
                {conflict.path1
                  ? `${formatBytes(conflict.path1Size ?? 0)}${
                      conflict.path1Modified ? ` · ${relativeTime(conflict.path1Modified)}` : ""
                    }`
                  : t("versão não encontrada")}
              </div>
              <div className="conflict-path mono">{conflict.path1 ?? "—"}</div>
            </div>
            <div className="conflict-side">
              <div className="conflict-tag">
                <Icon name="folder-open" size={13} />
                {t("Neste computador")}
              </div>
              <div className="conflict-name">{conflict.baseName}</div>
              <div className="conflict-meta">
                {conflict.path2
                  ? `${formatBytes(conflict.path2Size ?? 0)}${
                      conflict.path2Modified ? ` · ${relativeTime(conflict.path2Modified)}` : ""
                    }`
                  : t("versão não encontrada")}
              </div>
              <div className="conflict-path mono">{conflict.path2 ?? "—"}</div>
            </div>
            <div className="conflict-foot">
              <span className="badge warn">
                <Icon name="alert" size={12} />
                {conflict.folder}
              </span>
              <span style={{ flex: 1 }} />
              <button
                className="btn sm ghost"
                onClick={() => {
                  void api
                    .revealPath(conflict.localFolder)
                    .catch((cause) => notify(errorMessage(cause), "error"));
                }}
              >
                <Icon name="folder-open" size={14} />
                {t("Abrir pasta")}
              </button>
              <button
                className="btn sm ghost"
                disabled={!conflict.path1}
                onClick={() => setPending({ conflict, action: "remote" })}
              >
                <Icon name="cloud" size={14} />
                {t("Manter da nuvem")}
              </button>
              <button
                className="btn sm primary"
                disabled={!conflict.path2}
                onClick={() => setPending({ conflict, action: "local" })}
              >
                <Icon name="check" size={14} />
                {t("Manter a minha")}
              </button>
              <button
                className="btn sm ghost"
                disabled={!conflict.path1 || !conflict.path2}
                onClick={() => setPending({ conflict, action: "both" })}
              >
                {t("Manter as duas")}
              </button>
            </div>
          </article>
        ))
      )}

      <section className="card" style={{ marginTop: 20, padding: 18 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 10 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 15 }}>{t("Lixeira e versões anteriores")}</h3>
            <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
              {t("Arquivos sobrescritos ou apagados ficam guardados por 30 dias.")}
            </p>
          </div>
          {trash.length > 0 ? (
            <button className="btn sm ghost" onClick={() => void clearTrash()}>
              <Icon name="trash" size={14} />
              {t("Esvaziar lixeira")}
            </button>
          ) : null}
        </div>
        {trash.length === 0 ? (
          <p style={{ margin: 0, fontSize: 13, color: "var(--muted)" }}>
            {t("Nenhum arquivo na lixeira.")}
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {trash.map((item) => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: "var(--surface-2, rgba(0,0,0,0.03))",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.name}
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--muted)" }}>
                    {formatBytes(item.size)} · {relativeTime(item.deletedAt)}
                  </div>
                </div>
                <button className="btn sm ghost" onClick={() => void restoreItem(item)}>
                  <Icon name="download" size={13} />
                  {t("Restaurar")}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {pending ? (
        <Modal
          title={t(RESOLUTIONS[pending.action].title)}
          onClose={busy ? () => undefined : () => setPending(null)}
          footer={
            <>
              <button
                className="btn ghost"
                onClick={() => setPending(null)}
                disabled={busy}
              >
                {t("Cancelar")}
              </button>
              <button className="btn primary" onClick={() => void resolve()} disabled={busy}>
                {busy ? <Icon name="refresh" size={15} className="spin" /> : null}
                {t("Resolver")}
              </button>
            </>
          }
        >
          <p style={{ fontSize: 13, color: "var(--text-soft)" }}>
            {t(RESOLUTIONS[pending.action].description)}
          </p>
          <div className="banner info">
            <Icon name="shield" size={16} />
            {t(
              "A versão descartada fica guardada em “conflitos-resolvidos” dentro da configuração do BrisaSync.",
            )}
          </div>
          <p className="mono" style={{ fontSize: 11.5, color: "var(--muted)" }}>
            {pending.conflict.baseName}
          </p>
        </Modal>
      ) : null}
    </div>
  );
}
