import { Component, type ErrorInfo, type ReactNode } from "react";
import { t } from "../lib/i18n";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("BrisaSync UI error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px",
          background: "var(--bg, #f6f7f9)",
          color: "var(--text, #111827)",
        }}
      >
        <div
          className="card"
          style={{
            maxWidth: "440px",
            width: "100%",
            padding: "24px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <h2 style={{ margin: 0, fontSize: "18px" }}>{t("Algo deu errado.")}</h2>
          <p style={{ margin: 0, opacity: 0.8, fontSize: "14px", lineHeight: 1.5 }}>
            {t("Ocorreu um erro inesperado na interface. Você pode recarregar a janela para continuar.")}
          </p>
          {this.state.error.message && (
            <pre
              style={{
                margin: 0,
                padding: "10px 12px",
                borderRadius: "8px",
                background: "var(--surface-2, rgba(0,0,0,0.05))",
                fontSize: "12px",
                overflowX: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {this.state.error.message}
            </pre>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "4px" }}>
            <button
              className="btn primary"
              onClick={() => window.location.reload()}
            >
              {t("Recarregar")}
            </button>
          </div>
        </div>
      </div>
    );
  }
}
