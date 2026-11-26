import { describe, expect, it } from "vitest";
import { grupos, resumo } from "../lib/files";
import type { FileChange } from "../lib/types";

describe("files helpers", () => {
  const sample: FileChange[] = [
    { name: "a.txt", action: "sent" },
    { name: "b.txt", action: "sent" },
    { name: "c.txt", action: "received" },
  ];

  it("summarizes counts by action", () => {
    const r = resumo(sample);
    expect(r.find((item) => item.action === "sent")?.quantos).toBe(2);
    expect(r.find((item) => item.action === "received")?.quantos).toBe(1);
  });

  it("groups files by action", () => {
    const g = grupos(sample);
    expect(g.length).toBe(2);
    expect(g[0].itens.length).toBe(2);
  });
});
