import { useEffect, useState } from "react";
import { NOME, VERSAO } from "../lib/marca";
import { Doacoes } from "../components/Doacoes";
import { Icon } from "../components/Icons";
import { api, errorMessage, isDesktop } from "../lib/bridge";
import { IDIOMAS, useT } from "../lib/i18n";
import type {
  Account,
  EngineStatus,
  OAuthInfo,
  Settings as SettingsModel,
  UpdateInfo,
} from "../lib/types";

export function Settings({
  settings,
  theme,
  engine,
  accounts,
  autostart,
  autostartBusy,
  onUpdate,
  onTheme,
  onAutostart,
  onAddAccount,
  notify,
}: {
  settings: SettingsModel;
  theme: "light" | "dark";
  engine: EngineStatus | null;
  accounts: Account[];
  autostart: boolean;
  autostartBusy: boolean;
  onUpdate: (patch: Partial<SettingsModel>) => void;
  onTheme: (theme: "light" | "dark") => void;
  onAutostart: (enabled: boolean) => void;
  onAddAccount: () => void;
  notify: (message: string, kind?: "info" | "ok" | "error") => void;
}) {
  const t = useT();
  const [up, setUp] = useState(settings.bandwidthUp);
  const [down, setDown] = useState(settings.bandwidthDown);
  const [newRule, setNewRule] = useState("");
  const [clientId, setClientId] = useState(settings.driveClientId);
  const [clientSecret, setClientSecret] = useState(settings.driveClientSecret);
  const [mostrarSegredo, setMostrarSegredo] = useState(false);
  const [procurandoAtualizacao, setProcurandoAtualizacao] = useState(false);
  const [baixandoAtualizacao, setBaixandoAtualizacao] = useState(false);
  const [atualizacao, setAtualizacao] = useState<UpdateInfo | null>(null);

  const credenciaisProprias = Boolean(settings.driveClientId.trim());
  // Qual projeto OAuth o Google Drive está usando de fato: o do usuário, o
  // embutido no build (BrisaSync) ou o compartilhado do rclone.
  const [oauth, setOauth] = useState<OAuthInfo | null>(null);
  useEffect(() => {
    let vivo = true;
    void api
      .oauthInfo()
      .then((info) => {
        if (vivo) setOauth(info);
      })
      .catch(() => {
        if (vivo) setOauth(null);
      });
    return () => {
      vivo = false;
    };
  }, [settings.driveClientId, settings.driveClientSecret]);

  const fonteOauth: "usuario" | "nuvem" | "rclone" =
    oauth?.fonte ?? (credenciaisProprias ? "usuario" : "rclone");
  const rotuloOauth = {
    usuario: "seu projeto",
    nuvem: "projeto do BrisaSync",
    rclone: "projeto do rclone",
  }[fonteOauth]; // chave em português; traduzida em `t(rotuloOauth)`
  const driveConectado = accounts.some((account) => account.provider === "drive");

  const salvarCredenciais = () => {
    const id = clientId.trim();
    const segredo = clientSecret.trim();
    if (!id !== !segredo) {
      notify(
        t("Preencha o client_id e o client_secret juntos — ou deixe os dois em branco."),
        "error",
      );
      return;
    }
    if (id && !id.endsWith(".apps.googleusercontent.com")) {
      notify(t("O client_id do Google termina em .apps.googleusercontent.com."), "error");
      return;
    }
    onUpdate({ driveClientId: id, driveClientSecret: segredo });
    notify(
      id
        ? t("Credenciais salvas. As contas conectadas agora precisam ser autorizadas de novo.")
        : fonteOauth === "nuvem"
          ? t("Credenciais apagadas. O Google Drive volta a usar o projeto do BrisaSync.")
          : t("Credenciais apagadas. O Google Drive volta a usar o projeto do rclone."),
      "ok",
    );
  };

  const addRule = () => {
    const rule = newRule.trim();
    if (!rule) return;
    if (settings.ignoreRules.includes(rule)) {
      notify(t("Essa regra já existe."), "info");
      return;
    }
    onUpdate({ ignoreRules: [...settings.ignoreRules, rule] });
    setNewRule("");
  };

  return (
    <div className="settings-grid">
      <section className="card">
        <div className="card-head">
          <h2>{t("Contas")}</h2>
          <span className="spacer" />
          <button className="link" onClick={onAddAccount}>
            {t("Adicionar")}
          </button>
        </div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          {accounts.length === 0 ? (
            <p className="muted" style={{ fontSize: 12.5 }}>
              {t("Nenhuma conta conectada.")}
            </p>
          ) : (
            accounts.map((account) => (
              <div className="row" key={account.name}>
                <div className={`provider ${account.provider}`} style={{ width: 32, height: 32 }}>
                  <Icon name={account.provider === "drive" ? "drive" : "onedrive"} size={16} />
                </div>
                <div className="row-text">
                  <div className="row-title">{account.name}</div>
                  <div className="row-desc">{account.label}</div>
                </div>
                <div className="row-control">
                  {account.provider === "drive" ? (
                    account.clientOrigem === "usuario" ? (
                      <span className="badge ok" title={t("Autorizada com o seu projeto OAuth")}>
                        {t("cota própria")}
                      </span>
                    ) : account.clientOrigem === "nuvem" ? (
                      <span className="badge ok" title={t("Autorizada com o projeto OAuth do BrisaSync")}>
                        {t("cota do Nuvem")}
                      </span>
                    ) : (
                      <span
                        className="badge muted"
                        title={t(
                          "Autorizada no projeto OAuth compartilhado do rclone, de antes desta versão: reconecte a conta (em Avançado) para usar a cota do BrisaSync.",
                        )}
                      >
                        {t("projeto antigo · reconectar")}
                      </span>
                    )
                  ) : (
                    <span className="badge ok">{t("conectada")}</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>{t("Motor de sincronização")}</h2>
        </div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          <div className="row">
            <div className="row-text">
              <div className="row-title">rclone</div>
              <div className="row-desc mono">{engine?.binary ?? t("não encontrado")}</div>
            </div>
            <div className="row-control">
              <span className={`badge ${engine?.available ? "ok" : "danger"}`}>
                {engine?.version ?? t("indisponível")}
              </span>
            </div>
          </div>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Modo bisync")}</div>
              <div className="row-desc">
                {t("Duas vias, com ressincronização automática ao mudar caminhos.")}
              </div>
            </div>
            <div className="row-control">
              <span className="badge muted">{t("ativo")}</span>
            </div>
          </div>
          {!isDesktop ? (
            <div className="banner info" style={{ marginTop: 8 }}>
              <Icon name="info" size={16} />
              {t("Você está no modo demonstração (navegador).")}
            </div>
          ) : null}
          {engine && !engine.available ? (
            <div className="banner danger" style={{ marginTop: 8 }}>
              <Icon name="alert" size={16} />
              {t("Instale o rclone ou defina NUVEM_RCLONE.")}
            </div>
          ) : null}
        </div>
      </section>

      {/* Sincronização automática e intervalo */}
      <section className="card">
        <div className="card-head">
          <h2>{t("Sincronização")}</h2>
        </div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Sincronizar sozinho")}</div>
              <div className="row-desc">
                {t(
                  "Verifica as pastas e envia mudanças locais sem você pedir. Reage a arquivos novos em segundos e confere a nuvem no intervalo escolhido.",
                )}
              </div>
            </div>
            <div className="row-control">
              <button
                className={`switch ${settings.autoSync ? "on" : ""}`}
                role="switch"
                aria-checked={settings.autoSync}
                aria-label={t("Sincronizar automaticamente")}
                onClick={() => onUpdate({ autoSync: !settings.autoSync })}
              />
            </div>
          </div>

          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Conferir a nuvem a cada")}</div>
              <div className="row-desc">
                {t(
                  "Mudanças locais entram na hora; este intervalo pega o que mudou do outro lado.",
                )}
              </div>
            </div>
            <div className="row-control">
              <select
                className="select"
                aria-label={t("Intervalo da sincronização automática")}
                value={settings.syncIntervalMin}
                disabled={!settings.autoSync}
                onChange={(event) =>
                  onUpdate({ syncIntervalMin: Number(event.target.value) })
                }
              >
                <option value={1}>{t("1 minuto")}</option>
                <option value={5}>{t("5 minutos")}</option>
                <option value={15}>{t("15 minutos")}</option>
                <option value={30}>{t("30 minutos")}</option>
                <option value={60}>{t("1 hora")}</option>
              </select>
            </div>
          </div>

          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Tentar de novo sozinho")}</div>
              <div className="row-desc">
                {t(
                  "Repete a sincronização até 3 vezes (15 s, 60 s, 180 s) quando a falha parece ser de rede ou de limite do provedor.",
                )}
              </div>
            </div>
            <div className="row-control">
              <button
                className={`switch ${settings.autoRetry ? "on" : ""}`}
                role="switch"
                aria-checked={settings.autoRetry}
                aria-label={t("Repetir falhas transitórias")}
                onClick={() => onUpdate({ autoRetry: !settings.autoRetry })}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Aparência e Notificações */}
      <section className="card">
        <div className="card-head">
          <h2>{t("Aparência e Notificações")}</h2>
        </div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Idioma")}</div>
              <div className="row-desc">{t("Vale na hora, sem reiniciar o app.")}</div>
            </div>
            <div className="row-control">
              {IDIOMAS.map((item) => (
                <button
                  key={item.id}
                  className={`chip ${
                    (settings.language === "en" ? "en" : "pt") === item.id ? "active" : ""
                  }`}
                  onClick={() => onUpdate({ language: item.id })}
                  title={t(item.nome)}
                  aria-pressed={(settings.language === "en" ? "en" : "pt") === item.id}
                >
                  {t(item.nomeNativo)}
                </button>
              ))}
            </div>
          </div>

          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Tema")}</div>
              <div className="row-desc">{t("Segue sua preferência neste computador.")}</div>
            </div>
            <div className="row-control">
              <button
                className={`chip ${theme === "light" ? "active" : ""}`}
                onClick={() => onTheme("light")}
              >
                {t("Claro")}
              </button>
              <button
                className={`chip ${theme === "dark" ? "active" : ""}`}
                onClick={() => onTheme("dark")}
              >
                {t("Escuro")}
              </button>
            </div>
          </div>

          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Notificações")}</div>
              <div className="row-desc">{t("Avisar sobre conflitos e falhas.")}</div>
            </div>
            <div className="row-control">
              <button
                className={`switch ${settings.notifications ? "on" : ""}`}
                role="switch"
                aria-checked={settings.notifications}
                aria-label={t("Notificações")}
                onClick={() => onUpdate({ notifications: !settings.notifications })}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Banda e regras */}
      <section className="card">
        <div className="card-head">
          <h2>{t("Banda e regras")}</h2>
        </div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Limite de envio")}</div>
              <div className="row-desc">{t("Vazio = sem limite. Ex.: 5M, 800k.")}</div>
            </div>
            <div className="row-control">
              <input
                className="input sm"
                value={up}
                placeholder="∞"
                onChange={(event) => setUp(event.target.value)}
                aria-label={t("Limite de envio")}
              />
            </div>
          </div>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Limite de download")}</div>
              <div className="row-desc">{t("Aplicado na próxima sincronização.")}</div>
            </div>
            <div className="row-control">
              <input
                className="input sm"
                value={down}
                placeholder="∞"
                onChange={(event) => setDown(event.target.value)}
                aria-label={t("Limite de download")}
              />
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 10 }}>
            <button
              className="btn sm ghost"
              onClick={() => {
                onUpdate({ bandwidthUp: up.trim(), bandwidthDown: down.trim() });
                notify(t("Limites salvos."), "ok");
              }}
            >
              {t("Salvar limites")}
            </button>
          </div>

          <div className="divider" />

          <div className="row-title" style={{ fontSize: 12.5 }}>
            {t("Regras de ignorar")}
          </div>
          <div className="rules">
            {settings.ignoreRules.map((rule) => (
              <span className="rule" key={rule}>
                {rule}
                <button
                  aria-label={t("Remover regra {regra}", { regra: rule })}
                  onClick={() =>
                    onUpdate({
                      ignoreRules: settings.ignoreRules.filter((item) => item !== rule),
                    })
                  }
                >
                  <Icon name="x" size={11} />
                </button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <input
              className="input"
              value={newRule}
              placeholder={t("nova regra, ex.: *.iso")}
              onChange={(event) => setNewRule(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") addRule();
              }}
              aria-label={t("Nova regra de ignorar")}
            />
            <button className="btn sm ghost" onClick={addRule}>
              <Icon name="plus" size={14} />
            </button>
          </div>
        </div>
      </section>

      {/* Aplicativo e Sistema */}
      <section className="card">
        <div className="card-head">
          <h2>{t("Aplicativo e Sistema")}</h2>
        </div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Abrir com o sistema")}</div>
              <div className="row-desc">
                {autostartBusy
                  ? t("Aguardando o sistema confirmar…")
                  : t("Inicia minimizado na bandeja.")}
              </div>
            </div>
            <div className="row-control">
              <button
                className={`switch ${autostart ? "on" : ""}`}
                role="switch"
                aria-checked={autostart}
                aria-label={t("Iniciar com o sistema")}
                aria-busy={autostartBusy}
                disabled={autostartBusy}
                onClick={() => onAutostart(!autostart)}
              />
            </div>
          </div>

          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Fechar a janela encerra o app")}</div>
              <div className="row-desc">
                {settings.closeQuits
                  ? t("Sair da janela interrompe a sincronização. O aviso da bandeja deixa de aparecer.")
                  : t(
                      "Desligado, a janela some e o BrisaSync continua sincronizando na bandeja.",
                    )}
              </div>
            </div>
            <div className="row-control">
              <button
                className={`switch ${settings.closeQuits ? "on" : ""}`}
                role="switch"
                aria-checked={settings.closeQuits}
                aria-label={t("Fechar a janela encerra o app")}
                onClick={() => onUpdate({ closeQuits: !settings.closeQuits })}
              />
            </div>
          </div>

          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Configuração")}</div>
              <div className="row-desc">{t("Perfis e histórico do BrisaSync.")}</div>
            </div>
            <div className="row-control">
              <button
                className="btn sm ghost"
                onClick={() => {
                  void api
                    .openConfigFolder()
                    .then((path) => notify(t("Abrindo {caminho}", { caminho: path }), "info"))
                    .catch((cause) => notify(errorMessage(cause), "error"));
                }}
              >
                <Icon name="folder-open" size={14} />
                {t("Abrir")}
              </button>
            </div>
          </div>

          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Sair do BrisaSync")}</div>
              <div className="row-desc">
                {t("Interrompe a sincronização até abrir de novo.")}
              </div>
            </div>
            <div className="row-control">
              <button
                className="btn sm danger"
                onClick={() => {
                  void api.requestQuit();
                }}
              >
                {t("Sair")}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Apoie o projeto (Doações) */}
      <Doacoes notify={notify} />

      {/* Sobre */}
      <section className="card">
        <div className="card-head">
          <h2>{t("Sobre")}</h2>
        </div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{NOME} {VERSAO}</div>
              <div className="row-desc">Tauri · React · rclone</div>
            </div>
            <div className="row-control">
              <span className="badge muted">app.brisasync.BrisaSync</span>
            </div>
          </div>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Atualizações")}</div>
              <div className="row-desc">
                {atualizacao
                  ? t("A versão {versao} já está publicada.", { versao: atualizacao.version })
                  : t("Consulta a última versão publicada no repositório do projeto.")}
              </div>
            </div>
            <div className="row-control">
              {atualizacao ? (
                atualizacao.assetUrl && atualizacao.assetName ? (
                  <button
                    className="btn sm primary"
                    disabled={baixandoAtualizacao}
                    onClick={() => {
                      setBaixandoAtualizacao(true);
                      void api
                        .installUpdate(atualizacao.assetUrl!, atualizacao.assetName!)
                        .then((caminho) => {
                          notify(t("Atualização baixada em {caminho}", { caminho }), "ok");
                        })
                        .catch((cause) => notify(errorMessage(cause), "error"))
                        .finally(() => setBaixandoAtualizacao(false));
                    }}
                  >
                    <Icon
                      name={baixandoAtualizacao ? "refresh" : "download"}
                      size={14}
                      className={baixandoAtualizacao ? "spin" : undefined}
                    />
                    {baixandoAtualizacao ? t("Baixando…") : t("Atualizar agora")}
                  </button>
                ) : (
                  <button
                    className="btn sm primary"
                    onClick={() => {
                      void api
                        .openUrl(atualizacao.url)
                        .catch((cause) => notify(errorMessage(cause), "error"));
                    }}
                  >
                    <Icon name="download" size={14} />
                    {t("Baixar")}
                  </button>
                )
              ) : null}
              <button
                className="btn sm ghost"
                disabled={procurandoAtualizacao}
                onClick={() => {
                  setProcurandoAtualizacao(true);
                  void api
                    .checkUpdate()
                    .then((info) => {
                      setAtualizacao(info);
                      notify(
                        info
                          ? t("A versão {versao} está disponível.", {
                              versao: info.version,
                            })
                          : t("Você está na versão mais nova."),
                        info ? "info" : "ok",
                      );
                    })
                    .catch((cause) => notify(errorMessage(cause), "error"))
                    .finally(() => setProcurandoAtualizacao(false));
                }}
              >
                <Icon name="refresh" size={14} />
                {procurandoAtualizacao ? t("Procurando…") : t("Verificar")}
              </button>
            </div>
          </div>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Relatório de diagnóstico")}</div>
              <div className="row-desc">
                {t(
                  "Contas, pastas, ajustes e os últimos erros num arquivo de texto — sem senhas nem tokens. Útil ao abrir um problema no projeto.",
                )}
              </div>
            </div>
            <div className="row-control">
              <button
                className="btn sm ghost"
                onClick={() => {
                  void api
                    .saveDiagnostics()
                    .then((path) => notify(t("Relatório salvo em {caminho}", { caminho: path }), "ok"))
                    .catch((cause) => notify(errorMessage(cause), "error"));
                }}
              >
                <Icon name="file" size={14} />
                {t("Salvar")}
              </button>
            </div>
          </div>
          <div className="row">
            <div className="row-text">
              <div className="row-title">{t("Privacidade")}</div>
              <div className="row-desc">
                {t(
                  "Credenciais ficam na configuração local do rclone. O BrisaSync não envia dados para servidores próprios.",
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Avançado · Google Drive */}
      <section className="card" style={{ gridColumn: "1 / -1" }}>
        <div className="card-head">
          <h2>{t("Avançado · Google Drive")}</h2>
          <span className="spacer" />
          <span className={`badge ${fonteOauth === "rclone" ? "muted" : "ok"}`}>
            {t(rotuloOauth)}
          </span>
        </div>
        <div className="card-body" style={{ paddingTop: 10 }}>
          <div className="advanced">
            <div>
              <p className="muted" style={{ fontSize: 12.5 }}>
                {t(
                  "O Google cobra a cota de requisições por minuto no projeto OAuth usado na autorização. O projeto compartilhado do rclone é usado por todos os usuários dele e vive estourado — daí a sincronização arrastar mesmo com banda sobrando.",
                )}
              </p>
              <div className="row" style={{ padding: "10px 0", borderBottom: "none" }}>
                <div className="row-text">
                  <div className="row-title">{t("Projeto em uso")}</div>
                  <div className="row-desc mono" style={{ fontSize: 11.5, wordBreak: "break-all" }}>
                    {oauth?.clientId ?? t("sem client_id (projeto compartilhado do rclone)")}
                  </div>
                </div>
              </div>
              <p className="muted" style={{ fontSize: 12.5 }}>
                {fonteOauth === "nuvem"
                  ? t(
                      "Este build já usa o projeto OAuth do próprio BrisaSync: a cota é do aplicativo e não a do rclone. Preencha os campos abaixo só se quiser usar um projeto seu.",
                    )
                  : fonteOauth === "usuario"
                    ? t("As contas Google deste computador usam o projeto que você colou abaixo.")
                    : t(
                        "Sem projeto próprio, a cota é a do projeto compartilhado do rclone. Crie o seu para a fila ser só sua.",
                      )}
              </p>
              <p className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
                {t(
                  "1. Crie um projeto no Google Cloud, ative a Drive API e configure a tela de consentimento. 2. Em Credenciais, crie um ID do cliente OAuth do tipo app para computador. 3. Cole aqui os dois valores.",
                )}
              </p>

              {driveConectado ? (
                <div className="banner warn" style={{ marginTop: 12 }}>
                  <Icon name="info" size={16} />
                  {credenciaisProprias
                    ? t(
                        "As contas Google já conectadas continuam no projeto do rclone: remova as pastas que usam a conta, remova a conta em Visão geral → Contas e conecte de novo. O navegador pede a autorização uma vez.",
                      )
                    : t(
                        "Contas conectadas antes desta mudança só passam a usar as credenciais novas depois de removidas e conectadas de novo.",
                      )}
                </div>
              ) : null}

              <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
                {t("Fica salvo em")}{" "}
                <span className="mono">settings.json</span>
                {t(
                  ", neste computador, do mesmo jeito que o rclone guarda os tokens. Projeto no modo Testing do Google expira a autorização em 7 dias; publicar o app evita reautorizar toda semana.",
                )}
              </p>
            </div>

            <div>
              <div className="field">
                <label htmlFor="drive-client-id">client_id</label>
                <input
                  id="drive-client-id"
                  className="input mono"
                  value={clientId}
                  spellCheck={false}
                  autoComplete="off"
                  placeholder="123456789-abc.apps.googleusercontent.com"
                  onChange={(event) => setClientId(event.target.value)}
                />
              </div>

              <div className="field" style={{ marginTop: 10 }}>
                <label htmlFor="drive-client-secret">client_secret</label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    id="drive-client-secret"
                    className="input mono"
                    type={mostrarSegredo ? "text" : "password"}
                    value={clientSecret}
                    spellCheck={false}
                    autoComplete="off"
                    placeholder="GOCSPX-…"
                    onChange={(event) => setClientSecret(event.target.value)}
                  />
                  <button
                    className="btn sm ghost"
                    type="button"
                    aria-label={mostrarSegredo ? t("Ocultar segredo") : t("Mostrar segredo")}
                    onClick={() => setMostrarSegredo(!mostrarSegredo)}
                  >
                    {mostrarSegredo ? t("Ocultar") : t("Mostrar")}
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 12 }}>
                <button className="btn sm ghost" onClick={salvarCredenciais}>
                  {t("Salvar credenciais")}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
