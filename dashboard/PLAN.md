# Umsetzungsplan — user-zentrierter AngebotsBot

Stand: 2026-06-10. Basis: PERSONAS.md (10 Use Cases) + Playwright-Suite
(`tests/e2e/usecases.spec.ts`, aktuell 10/10 grün, UC3 nur mit Retry) +
Live-Datenanalyse (36k aktive Angebote, 13k frisch, 48 Märkte,
`offer_latest_category` leer).

Prioritäten: P0 = Verlässlichkeit, P1 = Datenqualität/Vertrauen,
P2 = neue user-zentrierte Features, P3 = Absicherung.
Aufwand: S (<½ Tag) · M (½–2 Tage) · L (>2 Tage).

---

## P0 — Verlässlichkeit der Datenbasis

### 0.1 `offer_deal_score` materialisieren — **M** *(Blocker für UC3, Basis für besseres Ranking)*
Die View aggregiert bei jedem Aufruf die komplette 90-Tage-`price_history`
(2–5 s warm, kalt > statement timeout → die Deals-Seite zeigte sporadisch
fälschlich "keine Daten"; im Testlauf reproduziert).
- Migration 009: `create materialized view offer_deal_score_mat` (gleiche
  Spalten + `last_seen_at`), unique Index auf `offer_id`, Index auf
  `price_percentile`.
- RPC `refresh_deal_scores()` (`refresh materialized view concurrently`),
  am Ende von `scripts/run_scrape.py` aufrufen.
- Dashboard auf die materialisierte View umstellen; Fehler-Empty-State bleibt
  als Fallback. Danach UC3-Retry-Toleranz entfernen.

### 0.2 LLM-Kategorisierung in Betrieb nehmen — **S–M**
`offer_latest_category` ist in Produktion leer — der Feed läuft rein
heuristisch. Der Concurrency-/RPC-Fix ist committet; der nächste Workflow-Run
muss beobachtet werden (`gh run watch`).
- Backfill in Tranchen: `python -m scripts.categorize_offers --limit 600`
  täglich via bestehendem Workflow, bis Backlog leer.
- Feed/Kategorien-Seite schalten automatisch auf LLM-Quelle um, sobald Daten
  da sind (Code existiert bereits); Heuristik bleibt Fallback.

### 0.3 Scrape-Stabilität beobachten — **S**
Timeout-Fix (50er-Chunks, Retry+Split) ist deployed. Erfolgskriterium:
5 grüne tägliche Runs in Folge; `last_seen_at`-Lücken (8-Tage-Frische) im
Dashboard verschwinden.

## P1 — Datenqualität & Vertrauen (Sabine, Gerd, Volker)

### 1.1 Mehrfachpackungs-Rabatte entschärfen — **M**
Befund: "Volvic 1,25 € statt 7,50 € (−83 %)" rankt den Feed hoch — Einzel-
vs. Kastenpreis. `discountTrust` greift nur bei Pack-Hinweis im Titel.
- Zusätzliche Regel: `original_price / price > 4` ⇒ suspect (egal welcher Titel).
- `price_condition_text` des Scrapers auswerten (steht dort oft "je Flasche").
- Feed-Ranking: suspect-Rabatte nicht mehr nach Rabatt ranken, sondern nach
  Preis-Percentil (braucht 0.1).

### 1.2 Deals-Seite user-tauglich machen — **M**
Volker sieht aktuell fast nur Möbelhäuser, und die Liste kann abgelaufene
Angebote enthalten.
- Stale-/Expired-Filter über `last_seen_at` aus 0.1.
- Filter-Chips: Kategorie-Bucket + "Nur meine Märkte" (liest Prefs).
- Mindest-Datenpunkte-Hinweis pro Zeile beibehalten.

## P2 — Neue user-zentrierte Features

### 2.1 Suche direkt im Feed (Tim) — **S**
Suchfeld auf der Startseite, das Markt-Präferenzen respektiert und die
bestehende `/stores`-Vergleichsansicht mit vorausgefülltem `q` verlinkt.

### 2.2 Merkliste / Einkaufszettel (Sabine) — **M**
Stern-Button an jeder `OfferRow` → localStorage-Liste, eigene Sektion oben im
Feed ("Dein Zettel"), Abhaken, Summe der Preise. Kein Backend nötig.

### 2.3 Unterkategorie-Präferenzen (Clara) — **S**
PrefsPanel: aufklappbare Subcategory-Chips pro gewähltem Bucket
(Taxonomie existiert); Feed filtert zusätzlich auf Subcategories.

### 2.4 Gespeicherte Suchen / Preisalarm light (Volker, Sven) — **M–L**
Phase 1 (ohne Backend): gespeicherte Suchbegriffe + Zielpreis in localStorage;
beim Feed-Load prüfen und als "Alarm"-Sektion zeigen.
Phase 2 (mit Backend): Supabase Auth + Edge Function + E-Mail/Push — erst
angehen, wenn Phase 1 genutzt wird.

### 2.5 PWA (Mia) — **S**
Web-App-Manifest + Icons, damit die App auf dem Homescreen installierbar ist.
(Push-Notifications erst mit 2.4 Phase 2.)

## P3 — Absicherung & Messung

### 3.1 Playwright in CI — **S**
GitHub Action: `npm run build && npm run start` + `npx playwright test`
gegen die Build-Ausgabe (Supabase-Read-Only via vorhandene Secrets).
Personas-Suite wird damit Regressionsschutz für jedes Deploy.

### 3.2 Test-Härtung — **S**
Nach 0.1: UC3 ohne Retry; UC5 um gezielten Fake-Rabatt-Datensatz ergänzen
(Fixture statt Live-Daten-Glück).

---

## Empfohlene Reihenfolge

| Sprint | Inhalt | Personas |
|---|---|---|
| 1 | 0.1 + 0.3 + 1.2 | Volker, alle (Verlässlichkeit) |
| 2 | 0.2 + 1.1 | Sabine, Gerd, Clara (Qualität) |
| 3 | 2.1 + 2.2 + 2.3 + 2.5 | Tim, Sabine, Clara, Mia |
| 4 | 2.4 + 3.1 + 3.2 | Volker, Sven + Regressionsschutz |
