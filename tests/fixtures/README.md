# Regression Fixtures

Diese Fixtures sind als wachsendes Vergleichs-Set gedacht.

`validity_cases.json`
- Rohtext aus einer Kaufda-Karte
- Referenzdatum für die Interpretation relativer Angaben wie `ab Donnerstag`
- Erwartete Normalisierung in `valid_from`, `valid_to`, `is_upcoming`

Später sinnvoll ergänzbar:
- Vision-Fälle mit lokalem Bildpfad oder stabiler Bild-URL
- Erwartete Felder wie `brand`, `product_name`, `deal_verdict`, `key_features`
- Grenzfälle mit schwer lesbaren Logos, zusammengesetzten Angeboten oder OCR-Artefakten
