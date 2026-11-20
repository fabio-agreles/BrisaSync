import { useCallback, useEffect, useMemo, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open } from "@tauri-apps/plugin-dialog";
import { Icon } from "../components/Icons";
import { api, errorMessage, isDesktop } from "../lib/bridge";
import { formatBytes, joinPath, parentPath } from "../lib/format";
import { locale, useT } from "../lib/i18n";
import type { Account, FolderSize, RemoteEntry } from "../lib/types";

export function Files({
  accounts,
  account,
  path,
  onAccount,
  onPath,
  onAddAccount,
  notify,
}: {
  accounts: Account[];
  /// Conta e caminho vivem no App: trocar de aba não pode perder a escolha.
  account: string;
  path: string;
  onAccount: (name: string) => void;
  onPath: (path: string) => void;
  onAddAccount: () => void;
  notify: (message: string, kind?: "info" | "ok" | "error") => void;
}) {
  const t = useT();
  const [entries, setEntries] = useState<RemoteEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [size, setSize] = useState<FolderSize | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(
    null,
  );
  const [dragging, setDragging] = useState(false);

  const load = useCallback(async () => {
    if (!account) return;
    setLoading(true);
    setError(null);
    try {
      const listing = await api.listRemote(account, path);
      setEntries(listing);
    } catch (cause) {
      setEntries([]);
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }

    // O tamanho total é uma segunda chamada (operations/size) e pode falhar
    // sozinho — não impede a listagem de aparecer.
    setSize(null);
    try {
      setSize(await api.folderSize(account, path));
    } catch {
      setSize(null);
    }
  }, [account, path]);

  const uploadPaths = useCallback(
    async (files: string[]) => {
      if (!account || files.length === 0) return;
      setBusy("upload");
      try {
        for (let index = 0; index < files.length; index += 1) {
          setUploadProgress({ current: index + 1, total: files.length });
          await api.uploadFile(account, path, files[index]);
        }
        notify(
          files.length === 1
            ? t("Enviado para {conta}:{caminho}.", { conta: account, caminho: path || "/" })
            : t("{n} arquivos enviados para {conta}:{caminho}.", {
                n: files.length,
                conta: account,
                caminho: path || "/",
              }),
          "ok",
        );
        await load();
      } catch (cause) {
        notify(errorMessage(cause), "error");
      } finally {
        setUploadProgress(null);
        setBusy(null);
      }
    },
    [account, path, load, notify, t],
  );

  const upload = useCallback(async () => {
    if (!account) return;
    if (isDesktop) {
      try {
        const picked = await open({
          multiple: true,
          title: t("Enviar arquivos para a nuvem"),
        });
        const files = Array.isArray(picked) ? picked : picked ? [picked] : [];
        if (files.length === 0) return;
        await uploadPaths(files);
      } catch (cause) {
        notify(errorMessage(cause), "error");
      }
    } else {
      setBusy("upload");
      try {
        const remote = await api.uploadFile(
          account,
          path,
          `/tmp/demonstracao/arquivo-${Date.now()}.txt`,
        );
        notify(t("Demonstração: {caminho} entrou na lista.", { caminho: remote }), "ok");
        await load();
      } catch (cause) {
        notify(errorMessage(cause), "error");
      } finally {
        setBusy(null);
      }
    }
  }, [account, path, load, notify, t, uploadPaths]);

  useEffect(() => {
    if (!isDesktop || !account) return;
    let active = true;
    let unlisten: (() => void) | undefined;
    void getCurrentWebview()
      .onDragDropEvent((event) => {
        if (!active) return;
        if (event.payload.type === "enter" || event.payload.type === "over") {
          setDragging(true);
        } else if (event.payload.type === "leave") {
          setDragging(false);
        } else if (event.payload.type === "drop") {
          setDragging(false);
          if (event.payload.paths.length > 0) {
            void uploadPaths(event.payload.paths);
          }
        }
      })
      .then((dispose) => {
        if (active) {
          unlisten = dispose;
        } else {
          dispose();
        }
      });
    return () => {
      active = false;
      setDragging(false);
      unlisten?.();
    };
  }, [account, uploadPaths]);

  const download = useCallback(
    async (entry: RemoteEntry) => {
      if (!account) return;
      setBusy(entry.path);
      try {
        let target = "/tmp/demonstracao";
        if (isDesktop) {
          const picked = await open({
            directory: true,
            title: t("Escolha a pasta para baixar"),
          });
          if (typeof picked !== "string") return;
          target = picked;
        }
        const saved = await api.downloadFile(account, entry.path, target);
        notify(t("Baixado para {caminho}", { caminho: saved }), "ok");
      } catch (cause) {
        notify(errorMessage(cause), "error");
      } finally {
        setBusy(null);
      }
    },
    [account, notify],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return entries;
    return entries.filter((entry) => entry.name.toLowerCase().includes(needle));
  }, [entries, query]);

  const segments = path.split("/").filter(Boolean);

  if (accounts.length === 0) {
    return (
      <section className="card">
        <div className="empty">
          <div className="empty-art">
            <Icon name="cloud" size={28} />
          </div>
          <h3>{t("Conecte uma conta para navegar")}</h3>
          <p>{t("Seus arquivos aparecem aqui sem precisar baixar nada antes.")}</p>
          <button className="btn primary" onClick={onAddAccount}>
            <Icon name="plus" size={16} />
            {t("Conectar conta")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <div
      className="files-wrap"
      onDragOver={(event) => {
        if (isDesktop) return;
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        if (isDesktop) return;
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setDragging(false);
      }}
      onDrop={(event) => {
        if (isDesktop) return;
        event.preventDefault();
        setDragging(false);
        const dropped = Array.from(event.dataTransfer.files).map(
          (file) => `/tmp/demonstracao/${file.name}`,
        );
        if (dropped.length > 0) {
          void uploadPaths(dropped);
        }
      }}
    >
      {dragging ? (
        <div className="dropzone-overlay">
          <div className="dropzone-icon">
            <Icon name="upload" size={24} />
          </div>
          <strong>
            {t("Solte aqui para enviar para {conta}:{caminho}", {
              conta: account,
              caminho: path || "/",
            })}
          </strong>
          <span>{t("Arquivos e pastas serão enviados para a pasta aberta.")}</span>
        </div>
      ) : null}
      <div className="toolbar">
        <select
          className="select"
          value={account}
          onChange={(event) => {
            onAccount(event.target.value);
            onPath("");
          }}
          aria-label={t("Conta")}
        >
          {accounts.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name} · {item.label}
            </option>
          ))}
        </select>

        <div className="breadcrumb">
          <button
            onClick={() => onPath("")}
            className={segments.length === 0 ? "current" : undefined}
          >
            {t("Início")}
          </button>
          {segments.map((segment, index) => {
            const target = segments.slice(0, index + 1).join("/");
            const last = index === segments.length - 1;
            return (
              <span key={target} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Icon name="chevron-right" size={13} />
                <button
                  onClick={() => onPath(target)}
                  className={last ? "current" : undefined}
                >
                  {segment}
                </button>
              </span>
            );
          })}
        </div>

        <span style={{ flex: 1 }} />

        <label className="search-field">
          <Icon name="search" size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("Filtrar nesta pasta")}
            aria-label={t("Filtrar arquivos")}
          />
        </label>

        <button
          className="btn primary small"
          onClick={() => void upload()}
          disabled={busy === "upload"}
          title={t("Enviar arquivos desta pasta do computador")}
        >
          <Icon name={busy === "upload" ? "refresh" : "upload"} size={15} className={busy === "upload" ? "spin" : undefined} />
          {uploadProgress
            ? t("Enviando {atual} de {total}…", {
                atual: uploadProgress.current,
                total: uploadProgress.total,
              })
            : t("Enviar")}
        </button>

        <button
          className="icon-btn"
          onClick={() => void load()}
          title={t("Atualizar")}
          aria-label={t("Atualizar listagem")}
        >
          <Icon name="refresh" size={17} className={loading ? "spin" : undefined} />
        </button>
      </div>

      <div className="files-summary">
        <span>
          <Icon name="cloud" size={14} />
          {account}:{path || "/"}
        </span>
        {size ? (
          <span className="muted">
            {size.count === 1 ? t("1 item") : t("{n} itens", { n: size.count })} ·{" "}
            {formatBytes(size.bytes)}
            {size.sizeless > 0
              ? t(" · {n} sem tamanho informado", { n: size.sizeless })
              : ""}
          </span>
        ) : null}
      </div>

      {error ? (
        <div className="banner danger" style={{ marginBottom: 14 }}>
          <Icon name="alert" size={16} />
          {error}
        </div>
      ) : null}

      <section className="card" style={{ overflow: "hidden" }}>
        {loading && entries.length === 0 ? (
          <div className="empty">
            <div className="empty-art">
              <Icon name="refresh" size={26} className="spin" />
            </div>
            <h3>{t("Lendo a nuvem…")}</h3>
            <p>{t("Listando {conta}:{caminho}", { conta: account, caminho: path || "/" })}</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <div className="empty-art">
              <Icon name={query ? "search" : "folder-open"} size={26} />
            </div>
            <h3>{query ? t("Nada encontrado") : t("Pasta vazia")}</h3>
            <p>
              {query
                ? t("Nenhum item corresponde a “{busca}”.", { busca: query })
                : t("Esta pasta não tem arquivos na nuvem. Você pode enviar um agora.")}
            </p>
          </div>
        ) : (
          <table className="file-table">
            <thead>
              <tr>
                <th>{t("Nome")}</th>
                <th>{t("Tamanho")}</th>
                <th>{t("Modificado")}</th>
                <th aria-label={t("Ações")} />
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <tr
                  key={entry.path}
                  className="file-row"
                  onClick={() => {
                    if (entry.isDir) {
                      onPath(entry.path);
                      setQuery("");
                    }
                  }}
                  tabIndex={entry.isDir ? 0 : -1}
                  onKeyDown={(event) => {
                    if (entry.isDir && (event.key === "Enter" || event.key === " ")) {
                      event.preventDefault();
                      onPath(entry.path);
                      setQuery("");
                    }
                  }}
                >
                  <td>
                    <div className="file-cell">
                      <span className={`file-ico ${entry.isDir ? "dir" : ""}`}>
                        <Icon name={entry.isDir ? "folder" : "file"} size={15} />
                      </span>
                      {entry.name}
                    </div>
                  </td>
                  <td>{entry.isDir ? "—" : formatBytes(entry.size)}</td>
                  <td>
                    {entry.modified
                      ? new Date(entry.modified).toLocaleDateString(locale())
                      : "—"}
                  </td>
                  <td>
                    <span className="row-actions">
                      {!entry.isDir ? (
                        <button
                          className="tiny-btn"
                          title={t("Baixar para o computador")}
                          aria-label={t("Baixar arquivo")}
                          onClick={(event) => {
                            event.stopPropagation();
                            void download(entry);
                          }}
                        >
                          <Icon
                            name={busy === entry.path ? "refresh" : "download"}
                            size={14}
                            className={busy === entry.path ? "spin" : undefined}
                          />
                        </button>
                      ) : null}
                      <button
                        className="tiny-btn"
                        title={entry.isDir ? t("Abrir") : t("Copiar caminho")}
                        aria-label={entry.isDir ? t("Abrir pasta") : t("Copiar caminho")}
                        onClick={(event) => {
                          event.stopPropagation();
                          if (entry.isDir) {
                            onPath(entry.path);
                            setQuery("");
                          } else {
                            void navigator.clipboard
                              ?.writeText(`${account}:${joinPath(path, entry.name)}`)
                              .then(() => notify(t("Caminho copiado."), "ok"))
                              .catch(() => notify(t("Não foi possível copiar."), "error"));
                          }
                        }}
                      >
                        <Icon name={entry.isDir ? "chevron-right" : "link"} size={14} />
                      </button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
        {t("Enviar e baixar arquivos avulsos não substitui uma pasta de sincronização: para manter tudo igual nos dois lados, crie um par em")}{" "}
        <strong>{t("Pastas")}</strong>.
        {path ? (
          <>
            {" "}
            <button
              className="link-btn"
              onClick={() => {
                onPath(parentPath(path));
                setQuery("");
              }}
            >
              {t("Voltar um nível")}
            </button>
          </>
        ) : null}
      </p>
    </div>
  );
}
