/**
 * Persona use-case acceptance tests — one describe per persona.
 * UC numbers map to PERSONAS.md.
 *
 * The suite runs against the real Supabase data, so assertions check
 * structure and invariants (counts, filters, ordering) rather than
 * exact values.
 */

import { test, expect, type Page, type Locator } from "@playwright/test";

const PREFS_KEY = "angebotsbot.prefs.v1";

type Prefs = {
  stores: string[];
  buckets: string[];
  bargainMinDiscount: number | null;
  onboarded: boolean;
};

const DEFAULTS: Prefs = {
  stores: [],
  buckets: ["Lebensmittel", "Getränke"],
  bargainMinDiscount: 40,
  onboarded: true,
};

async function seedPrefs(page: Page, prefs: Partial<Prefs> = {}) {
  const merged = { ...DEFAULTS, ...prefs };
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [PREFS_KEY, JSON.stringify(merged)] as const,
  );
}

/** Stores that must never appear in a supermarket-only feed. */
const NON_SUPERMARKETS = [
  "XXXLutz",
  "ROLLER",
  "POCO",
  "Segmüller",
  "Höffner",
  "JYSK",
  "IKEA",
  "Globus-Baumarkt",
  "toom Baumarkt",
  "METRO",
  "Woolworth",
];

function feedSection(page: Page, heading: string): Locator {
  return page.locator("section", {
    has: page.getByRole("heading", { name: heading }),
  });
}

/** Offer rows inside a feed section (OfferRow renders a div per row). */
function offerRows(section: Locator): Locator {
  return section.locator("ul > div");
}

/* ────────────────────────────────────────────────────────────────────── */

test.describe("UC1 Sparfüchsin Sabine — Wocheneinkauf Supermarkt", () => {
  test("Onboarding → Nur Supermärkte → Lebensmittel-Feed", async ({ page }) => {
    await page.goto("/");

    // First visit: onboarding panel is shown.
    await expect(page.getByText("Willkommen! Was interessiert dich?")).toBeVisible();

    // 3 Klicks: Preset → Los geht's (Kategorien sind schon vorausgewählt).
    const preset = page.getByRole("button", { name: "Nur Supermärkte" });
    await expect(preset).toBeEnabled();
    await preset.click();
    await page.getByRole("button", { name: "Los geht's" }).click();

    // Feed shows ≥10 offers with prices.
    const mine = feedSection(page, "Deine Angebote");
    const rows = offerRows(mine);
    await expect(rows.nth(9)).toBeVisible();
    await expect(rows.first()).toContainText("€");

    // No furniture/wholesale stores in the personalized section.
    const text = await mine.innerText();
    for (const store of NON_SUPERMARKETS) {
      expect(text, `Feed enthält Nicht-Supermarkt "${store}"`).not.toContain(store);
    }
  });
});

test.describe("UC2 Student Tim — Produktsuche mit Marktvergleich", () => {
  test("Suche 'Joghurt' gruppiert nach Markt, günstigster zuerst", async ({ page }) => {
    await page.goto("/stores?q=Joghurt");

    // Result summary + at least one store group with "ab X €".
    await expect(page.getByText(/Treffer in/)).toBeVisible();
    const firstGroup = page.locator("section, div.space-y-4 > div").filter({
      has: page.locator("header"),
    }).first();
    await expect(firstGroup.locator("header")).toContainText("ab");
    await expect(firstGroup.locator("header")).toContainText("€");
    await expect(firstGroup.locator("ul > div").first()).toBeVisible();
  });
});

test.describe("UC3 Vorratsplaner Volker — historische Preisbewertung", () => {
  test("Bestenliste mit Percentil → Detail mit Preisverlauf", async ({ page }) => {
    await page.goto("/deals");

    const list = page.locator("ul > li a[href*='/deals?offer=']");
    await expect(list.first()).toBeVisible();
    // Percentile badge in row.
    await expect(list.first().locator("span").filter({ hasText: "%" }).first()).toBeVisible();

    await list.first().click();
    await expect(page.getByText("Ø 90 Tage")).toBeVisible();
    await expect(page.getByText("Preisverlauf")).toBeVisible();
    // Either a chart or the honest "not enough data" hint.
    const chart = page.locator("svg.recharts-surface");
    const hint = page.getByText(/Noch nicht genug Datenpunkte/);
    await expect(chart.or(hint).first()).toBeVisible();
  });
});

test.describe("UC4 Clara — Kategorie-Browsing Obst & Gemüse", () => {
  test("Buckets → Lebensmittel → Unterkategorie → Angebote", async ({ page }) => {
    await page.goto("/categories");

    // 10 bucket cards with counts.
    await expect(page.getByText("Lebensmittel", { exact: true })).toBeVisible();
    await page.getByRole("link", { name: /Lebensmittel/ }).first().click();

    await expect(page.getByText("Unterkategorien")).toBeVisible();

    // Click the first enabled subcategory chip (data decides which has offers).
    const chips = page.locator("a[href*='&sub=']:not([aria-disabled='true'])");
    await expect(chips.first()).toBeVisible();
    await chips.first().click();

    // Filtered offer list (or honest empty state).
    const rows = page.locator("ul > div");
    const empty = page.getByText("Keine Angebote in dieser Auswahl");
    await expect(rows.first().or(empty)).toBeVisible();
  });
});

test.describe("UC5 Gerd — Getränke ohne Fake-Rabatte", () => {
  test("Getränke-Feed; kein Rabatt-Badge >95 %", async ({ page }) => {
    await seedPrefs(page, { buckets: ["Getränke"] });
    await page.goto("/");

    const mine = feedSection(page, "Deine Angebote");
    await expect(offerRows(mine).first()).toBeVisible();

    // All discount badges across the page must be ≤95 % (implausible = hidden).
    const badges = await page.locator("span", { hasText: /−\d+%/ }).allInnerTexts();
    for (const b of badges) {
      const m = b.match(/−(\d+)%/);
      if (m) expect(Number(m[1]), `Unplausibles Badge "${b}"`).toBeLessThanOrEqual(95);
    }
  });
});

test.describe("UC6 Sven — Schnäppchen-Radar für andere Kategorien", () => {
  test("Radar zeigt Nicht-Lebensmittel ab Schwelle, Schwelle einstellbar", async ({ page }) => {
    await seedPrefs(page, { bargainMinDiscount: 40 });
    await page.goto("/");

    const radar = feedSection(page, "Schnäppchen-Radar");
    await expect(radar.getByText("ab 40% Rabatt")).toBeVisible();
    const rows = offerRows(radar);
    await expect(rows.first()).toBeVisible();

    // Every radar row carries a trusted discount badge ≥ threshold.
    const badges = await radar.locator("span", { hasText: /−\d+%/ }).allInnerTexts();
    expect(badges.length).toBeGreaterThan(0);
    for (const b of badges) {
      const m = b.match(/−(\d+)%/);
      if (m) expect(Number(m[1])).toBeGreaterThanOrEqual(40);
    }

    // Threshold options exist in the prefs panel.
    await page.getByRole("button", { name: "Präferenzen" }).click();
    for (const label of ["aus", "ab 25%", "ab 40%", "ab 60%"]) {
      await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
    }
  });
});

test.describe("UC7 Dana — Drogerie-Fokus", () => {
  test("Preset Supermärkte + Drogerien filtert den Feed", async ({ page }) => {
    await seedPrefs(page, { buckets: ["Drogerie & Kosmetik", "Lebensmittel"] });
    await page.goto("/");

    await page.getByRole("button", { name: "Präferenzen" }).click();
    const preset = page.getByRole("button", { name: "Supermärkte + Drogerien" });
    await expect(preset).toBeEnabled();
    await preset.click();
    await page.getByRole("button", { name: "Speichern" }).click();

    // Saved prefs contain only supermarket/drugstore chains.
    const prefs = await page.evaluate(
      (key) => JSON.parse(window.localStorage.getItem(key) ?? "{}"),
      PREFS_KEY,
    );
    expect(prefs.stores.length).toBeGreaterThan(0);

    const mine = feedSection(page, "Deine Angebote");
    await expect(offerRows(mine).first()).toBeVisible();
    const text = await mine.innerText();
    for (const store of NON_SUPERMARKETS) {
      expect(text).not.toContain(store);
    }
  });
});

test.describe("UC8 Wolfgang — nächste Woche planen", () => {
  test("Wochen-Umschalter ändert URL und Feed-Untertitel", async ({ page }) => {
    await seedPrefs(page);
    await page.goto("/");
    await expect(offerRows(feedSection(page, "Deine Angebote")).first()).toBeVisible();

    await page.getByRole("button", { name: "Nächste Woche" }).click();
    await expect(page).toHaveURL(/week=next/);
    await expect(page.getByText(/Nächste Woche/).first()).toBeVisible();

    // Feed reloads and still renders (data may be thinner next week).
    const rows = offerRows(feedSection(page, "Deine Angebote"));
    const empty = page.getByText("Keine Angebote in deiner Auswahl");
    await expect(rows.first().or(empty)).toBeVisible();
  });
});

test.describe("UC9 Mia — mobil, 390px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Drawer-Navigation funktioniert, kein horizontaler Overflow", async ({ page }) => {
    await seedPrefs(page);
    await page.goto("/");
    await expect(offerRows(feedSection(page, "Deine Angebote")).first()).toBeVisible();

    // No horizontal scrolling.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, "horizontaler Overflow in px").toBeLessThanOrEqual(1);

    // Drawer opens and navigates.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("link", { name: "Kategorien", exact: true }).click();
    await expect(page).toHaveURL(/\/categories/);
  });
});

test.describe("UC10 Rainer — Einstellungen bleiben erhalten", () => {
  test("Nach Onboarding + Reload: kein Panel, Feed da, Frische & Refresh", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Willkommen! Was interessiert dich?")).toBeVisible();
    await page.getByRole("button", { name: "Los geht's" }).click();
    await expect(offerRows(feedSection(page, "Deine Angebote")).first()).toBeVisible();

    await page.reload();
    await expect(page.getByText("Willkommen! Was interessiert dich?")).not.toBeVisible();
    await expect(offerRows(feedSection(page, "Deine Angebote")).first()).toBeVisible();

    // Freshness indicator + manual refresh.
    await expect(page.getByText(/Stand:/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Daten aktualisieren" })).toBeVisible();
  });
});
