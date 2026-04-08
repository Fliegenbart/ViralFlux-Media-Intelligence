# Security Cleanup Plan

**Ziel:** Die größten Sicherheits- und Wartungsrisiken zuerst schließen, ohne die bestehende App unnötig zu destabilisieren.

## Phase 1: Akute Risiken schließen

- Offenen `/api/v1/outbreak-score/peix-score` so umbauen, dass die Landing-Page weiter funktioniert, aber keine internen Modell-Details öffentlich bleiben.
- Schreibenden CRM-Export aus `GET /api/v1/marketing/export/crm` herauslösen und auf einen mutierenden `POST`-Pfad umstellen.
- Passende Backend-Tests ergänzen und betroffene Doku anpassen.

## Phase 2: Auth und Session wirklich härten

- Login-Antwort so umbauen, dass kein lesbares Bearer-Token mehr im Response-Body zurückkommt.
- Logout serverseitig härten, damit gestohlene Tokens nicht einfach bis zum Ablauf weiter funktionieren.
- Prozesslokale Login-Sperre in eine robustere, instanzübergreifende Lösung überführen.
- Prüfen, ob für Cookie-basierte Schreibzugriffe zusätzlicher CSRF-Schutz nötig ist.

## Phase 3: Spaghetti-Code abbauen

- `frontend/src/features/media/useMediaData.ts` in kleinere, seitenbezogene Hooks aufteilen.
- `backend/app/services/marketing_engine/opportunity_engine.py` in klar getrennte Verantwortlichkeiten zerlegen.
- Upload-Validierung vereinheitlichen, doppelte Konstanten zentralisieren und versteckte Seiteneffekte aus Lesewegen entfernen.

## Reihenfolge

1. Zuerst die akuten Exploit- und Datenleck-Risiken.
2. Danach die noch halbfertige Auth-Härtung.
3. Zum Schluss die strukturelle Aufräumarbeit für bessere Wartbarkeit.
