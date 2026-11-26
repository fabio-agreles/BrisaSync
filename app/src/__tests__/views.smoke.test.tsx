import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { Activity } from "../views/Activity";
import type { ActivityEntry } from "../lib/types";

describe("UI smoke tests", () => {
  it("filters Activity entries by search query", () => {
    const entries: ActivityEntry[] = [
      {
        id: "1",
        kind: "upload",
        title: "Relatório enviado",
        detail: "Pasta Trabalho",
        at: Date.now(),
        profile: null,
        files: [{ name: "relatorio-2026.pdf", action: "sent" }],
      },
      {
        id: "2",
        kind: "download",
        title: "Foto baixada",
        detail: "Pasta Pessoal",
        at: Date.now(),
        profile: null,
        files: [{ name: "ferias.jpg", action: "received" }],
      },
    ];

    render(<Activity entries={entries} onClear={vi.fn().mockResolvedValue(undefined)} />);
    expect(screen.getByText("Relatório enviado")).toBeInTheDocument();
    expect(screen.getByText("Foto baixada")).toBeInTheDocument();

    const search = screen.getByPlaceholderText("Buscar na atividade...");
    fireEvent.change(search, { target: { value: "ferias" } });

    expect(screen.queryByText("Relatório enviado")).not.toBeInTheDocument();
    expect(screen.getByText("Foto baixada")).toBeInTheDocument();
  });

  it("renders fallback UI when ErrorBoundary catches an error", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error("falha simulada");
    }

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByText("Algo deu errado.")).toBeInTheDocument();
    expect(screen.getByText("falha simulada")).toBeInTheDocument();
    spy.mockRestore();
  });
});
