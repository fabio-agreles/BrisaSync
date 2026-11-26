import { afterEach, describe, expect, it } from "vitest";
import { definirIdioma, t } from "../lib/i18n";

describe("i18n", () => {
  afterEach(() => {
    definirIdioma("pt");
  });

  it("translates known keys to English and interpolates values", () => {
    definirIdioma("en");
    expect(t("Ajustes")).toBe("Settings");
    expect(t("{n} itens", { n: 5 })).toBe("5 items");
  });

  it("keeps Portuguese text when language is pt", () => {
    definirIdioma("pt");
    expect(t("Ajustes")).toBe("Ajustes");
    expect(t("{n} itens", { n: 3 })).toBe("3 itens");
  });
});
