import { useState } from "react";
import qrPix from "../assets/pix-qr.svg";
import {
  CHAVE_PIX,
  DOACAO_PARAGRAFOS,
  DOACAO_RESUMO,
  DOACAO_TITULO,
  PIX_COPIA_E_COLA,
} from "../lib/doacoes";
import { useT } from "../lib/i18n";
import { Icon } from "./Icons";
import { Modal } from "./Modal";

// WebKitGTK nem sempre expõe navigator.clipboard na janela do app; o textarea
// escondido com execCommand("copy") é o plano B — mesmo truque do "copiar
// caminho" em Arquivos.
async function copiarTexto(texto: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(texto);
      return true;
    }
  } catch {
    // cai no plano B
  }
  try {
    const area = document.createElement("textarea");
    area.value = texto;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const copiou = document.execCommand("copy");
    document.body.removeChild(area);
    return copiou;
  } catch {
    return false;
  }
}

// Cartão + diálogo de doações. O QR é um BR Code estático gerado por
// scripts/gerar-pix.sh (o mesmo texto que o botão copia), então quem lê o QR com
// a câmera e quem usa "Pix copia e cola" cai na mesma chave.
export function Doacoes({
  notify,
}: {
  notify: (message: string, kind?: "info" | "ok" | "error") => void;
}) {
  const t = useT();
  const [aberto, setAberto] = useState(false);

  const copiar = async () => {
    const copiou = await copiarTexto(PIX_COPIA_E_COLA);
    notify(
      copiou
        ? t("Código Pix copiado. Cole no app do banco.")
        : t("Não foi possível copiar o código Pix."),
      copiou ? "ok" : "error",
    );
  };

  return (
    <>
      <section className="card doacao">
        <div className="doacao-mark">
          <Icon name="heart" size={20} />
        </div>
        <div className="doacao-text">
          <div className="doacao-title">{t(DOACAO_TITULO)}</div>
          <div className="row-desc">{t(DOACAO_RESUMO)}</div>
        </div>
        <div className="row-control">
          <button className="btn sm primary" onClick={() => setAberto(true)}>
            <Icon name="heart" size={14} />
            {t("Doar com Pix")}
          </button>
        </div>
      </section>

      {aberto ? (
        <Modal
          title={t(DOACAO_TITULO)}
          onClose={() => setAberto(false)}
          footer={
            <>
              <button className="btn sm ghost" onClick={() => setAberto(false)}>
                {t("Fechar")}
              </button>
              <button className="btn sm primary" onClick={() => void copiar()}>
                <Icon name="copy" size={14} />
                {t("Copiar código Pix")}
              </button>
            </>
          }
        >
          <div className="doacao-texto">
            {DOACAO_PARAGRAFOS.map((paragrafo) => (
              <p key={paragrafo}>{t(paragrafo)}</p>
            ))}
          </div>

          <div className="pix">
            <div className="pix-qr">
              <img src={qrPix} alt={t("QR code para doação via Pix")} />
            </div>
            <div className="pix-info">
              <div className="pix-label">{t("Chave Pix")}</div>
              <div className="pix-chave mono">{CHAVE_PIX}</div>
              <p className="pix-dica">
                {t(
                  "Aponte a câmera do celular para o QR ou use o botão abaixo para copiar o código e colar no app do banco em",
                )}{" "}
                <strong>{t("Pix → Pix copia e cola")}</strong>.
              </p>
            </div>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
