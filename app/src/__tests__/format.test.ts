import { describe, expect, it } from "vitest";
import { formatBytes, formatEta, joinPath, parentPath } from "../lib/format";

describe("format", () => {
  it("formats bytes across units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1024)).toBe("1,0 KB");
    expect(formatBytes(1024 * 1024)).toBe("1,0 MB");
  });

  it("formats ETA", () => {
    expect(formatEta(null)).toBe("—");
    expect(formatEta(45)).toBe("45 s");
    expect(formatEta(125)).toBe("2 min 5 s");
  });

  it("computes parentPath and joinPath", () => {
    expect(parentPath("")).toBe("");
    expect(parentPath("a/b/c")).toBe("a/b");
    expect(parentPath("a")).toBe("");
    expect(joinPath("", "doc.pdf")).toBe("doc.pdf");
    expect(joinPath("a/b", "doc.pdf")).toBe("a/b/doc.pdf");
  });
});
