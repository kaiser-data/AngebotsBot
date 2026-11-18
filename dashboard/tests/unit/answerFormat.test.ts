import { describe, expect, it } from "vitest";
import { parseAnswer, parseInline } from "@/lib/answerFormat";

describe("parseAnswer (real answer from the live site)", () => {
  const answer = `Diese Woche ist Butter am günstigsten bei Netto Marken-Discount und EDEKA:

*   Bei **Netto Marken-Discount** erhältst du [Weihenstephan Butter oder Streichzart](#0e7bfea4-4e02-4280-84b1-e33f61d0ace8) für nur 0,99 €.
*   Ebenfalls für 0,99 € gibt es bei **EDEKA** [Arla Kærgården](#f33c9c2f-161d-496d-a93e-3dca9757c819).`;

  it("splits paragraphs and bullets, drops blank lines", () => {
    const blocks = parseAnswer(answer);
    expect(blocks.map((b) => b.bullet)).toEqual([false, true, true]);
  });

  it("turns offer links into names — no UUIDs or brackets left in the text", () => {
    const parts = parseAnswer(answer)[1].parts;
    expect(parts).toContainEqual({ kind: "bold", text: "Netto Marken-Discount" });
    expect(parts).toContainEqual({
      kind: "offer", text: "Weihenstephan Butter oder Streichzart", id: "0e7bfea4-4e02-4280-84b1-e33f61d0ace8",
    });
    const visible = parts.map((p) => p.text).join("");
    expect(visible).not.toMatch(/[[\]*#]|0e7bfea4/);
    expect(visible).toContain("für nur 0,99 €.");
  });
});

describe("parseInline edge cases", () => {
  it("leaves plain text alone", () => {
    expect(parseInline("Keine Angebote.")).toEqual([{ kind: "text", text: "Keine Angebote." }]);
  });
  it("does not treat external links or HTML as markup", () => {
    expect(parseInline("[x](https://evil.example) <b>y</b>")).toEqual([
      { kind: "text", text: "[x](https://evil.example) <b>y</b>" },
    ]);
  });
  it("keeps an unmatched ** as text", () => {
    expect(parseInline("2 ** 3")).toEqual([{ kind: "text", text: "2 ** 3" }]);
  });
});
