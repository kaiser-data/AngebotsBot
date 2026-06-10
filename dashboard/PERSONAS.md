# Personas & Use Cases

Zehn Personas mit unterschiedlichen Interessen und Zielen. Jeder Use Case hat
messbare Akzeptanzkriterien, die als Playwright-Tests in
`tests/e2e/usecases.spec.ts` kodiert sind (UC-Nummern = Test-Nummern).

Testlauf: `npx playwright test` (startet den Dev-Server automatisch).

---

## UC1 — Sparfüchsin Sabine (38, Familienmutter)
**Ziel:** Den Wocheneinkauf für die Familie so günstig wie möglich planen.
**Verhalten:** Öffnet die App einmal pro Woche, will ohne Suchen sofort die
besten Lebensmittel-Angebote der Supermärkte sehen.
**Akzeptanz:**
- Beim ersten Besuch kann sie in ≤3 Klicks "Nur Supermärkte" + Lebensmittel-Fokus wählen.
- Danach zeigt die Startseite ≥10 Lebensmittel-/Getränke-Angebote mit Preis.
- Alle Angebote stammen aus Supermärkten/Discountern.

## UC2 — Student Tim (23, knappes Budget)
**Ziel:** Ein konkretes Produkt (z. B. Joghurt) zum tiefsten Preis finden.
**Verhalten:** Sucht gezielt und vergleicht Märkte.
**Akzeptanz:**
- Suche nach "Joghurt" liefert Treffer, gruppiert nach Markt.
- Innerhalb der Gruppen ist der günstigste Preis zuerst sichtbar ("ab X €").

## UC3 — Vorratsplaner Volker (45, kauft auf Vorrat)
**Ziel:** Nur zuschlagen, wenn ein Preis historisch wirklich gut ist.
**Verhalten:** Prüft Preisverlauf, bevor er groß einkauft.
**Akzeptanz:**
- Eine Bestenliste zeigt Angebote mit Preis-Percentil (niedriger = besser).
- Klick auf ein Angebot zeigt Detailseite mit aktuellem Preis, 90-Tage-Schnitt
  und Preisverlauf (oder ehrlichem Hinweis bei zu wenig Datenpunkten).

## UC4 — Kategorie-Browserin Clara (31, kocht viel frisch)
**Ziel:** Gezielt in "Obst & Gemüse" stöbern statt suchen.
**Akzeptanz:**
- Kategorien-Seite zeigt die 10 Buckets mit Angebots-Zahlen.
- Lebensmittel → Unterkategorie wählbar → gefilterte Angebotsliste erscheint.

## UC5 — Getränke-Fan Gerd (52, kauft Kästen)
**Ziel:** Bier-/Wasser-Deals finden, ohne auf Fake-Rabatte hereinzufallen.
**Verhalten:** Misstraut "−90 %"-Angeboten bei Kästen.
**Akzeptanz:**
- Feed mit Bucket "Getränke" zeigt Getränke-Angebote.
- Unplausible Rabatte (>95 %) werden nirgends als Badge angezeigt;
  verdächtige Pack-Rabatte tragen ein Warn-Badge.

## UC6 — Schnäppchenjäger Sven (29, kauft opportunistisch)
**Ziel:** Mega-Deals außerhalb der Lebensmittel sehen (Elektronik, Möbel …),
aber nur wenn der Rabatt es wert ist.
**Akzeptanz:**
- Startseite hat einen "Schnäppchen-Radar" mit Nicht-Lebensmittel-Angeboten,
  alle mit Rabatt ≥ der eingestellten Schwelle.
- Schwelle ist einstellbar (aus / 25 / 40 / 60 %).

## UC7 — Drogerie-Käuferin Dana (27)
**Ziel:** Drogerie-Angebote (dm, Rossmann, Müller) im Blick behalten.
**Akzeptanz:**
- Preset "Supermärkte + Drogerien" wählbar; alternativ einzelne Märkte.
- Feed respektiert die Markt-Auswahl (keine fremden Märkte).

## UC8 — Wochenplaner Wolfgang (60, plant voraus)
**Ziel:** Schon heute die Angebote der nächsten Woche kennen.
**Akzeptanz:**
- Umschalter "Nächste Woche" existiert auf jeder Seite und ändert die Daten
  (URL-Parameter `week=next`, Feed lädt neu).

## UC9 — Mobile-Nutzerin Mia (24, nur Smartphone)
**Ziel:** Alles unterwegs am Handy erledigen.
**Akzeptanz:**
- Bei 390 px Breite: Navigation über Drawer erreichbar, Feed lesbar,
  kein horizontales Scrollen.

## UC10 — Wiederkehrender Nutzer Rainer (41, Gewohnheitstier)
**Ziel:** App merkt sich seine Einstellungen — null Reibung beim 2. Besuch.
**Akzeptanz:**
- Nach Onboarding und Reload: kein Onboarding-Panel mehr, Feed direkt
  nach gespeicherten Präferenzen gefiltert.
- Frische-Anzeige ("Stand: …") und manueller Refresh vorhanden.
