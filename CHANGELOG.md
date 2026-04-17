# Changelog

## 2026-04-17 — Cockpit-Pivot und Gallery-Refresh

### Cockpit als einzige user-facing Surface

- `/cockpit` ist seit diesem Stand die einzige live gerenderte Seite
- alle bisherigen Routes (`/login`, `/welcome`, `/virus-radar`, `/jetzt`, `/zeitgraph`, `/regionen`, `/kampagnen`, `/evidenz`, `/dashboard`, `/entscheidung`, `/lagebild`, `/pilot`, `/bericht`, `/empfehlungen`, `/validierung`, `/backtest`) leiten client-seitig nach `/cockpit` um — alte Bookmarks 404en nicht
- shared-password Gate loest den bisherigen OAuth-Login ab: `POST /api/v1/media/cockpit/unlock` validiert das Passwort aus `COCKPIT_ACCESS_PASSWORD` und setzt ein HMAC-signiertes Cookie (30 Tage). Drei Zugangsarten gleichzeitig: Session-Cookie, `X-API-Key` (M2M), `cockpit_unlock`-Cookie (Gate)
- `frontend/public/robots.txt` mit `Disallow: /` verhindert Indexierung

### Gallery-Design-Refresh der vier Tabs

- Atlas-Aesthetik als gemeinsames Design-System extrahiert: warm-schwarze Gallery-Stage, editorial Split-Komposition, eine Terracotta-Akzentfarbe, drei Schriften mit klaren Rollen (Fraunces / JetBrains Mono / Inter Tight), Roster-Pattern, Caption-Strip
- neue shared Components `GalleryHero.tsx`, `RosterList.tsx`, neues Stylesheet `peix-gallery.css`
- Decision / Timeline / Impact komplett neu gezogen — weniger, groessere Cards, deutlich mehr Weissraum
- warm-tint / cool-tint / ink-Gradienten entfernt zugunsten ruhiger paper-quiet-Cards unter dem dunklen Hero

### Atlas 3D-Map Polish

- "Zuppel"-Artefakt behoben: breath-Animation durch signed sin² easing (14 s Periode, geschwindigkeit faellt smooth gegen 0 an den Umkehrpunkten)
- IntersectionObserver pausiert rAF wenn Canvas offscreen
- resize-Handler gehaertet (3 px Delta-Gate, setPixelRatio re-assert, setSize ohne CSS-Write)
- `contain: layout size` auf `.peix-sculpture__canvas` isoliert das Canvas von Parent-Layout-Jitter

## Frontend-Modernisierung (Historie)

Der aktuelle Frontend-Stand ist nicht mehr nur ein klassisches Dashboard, sondern stärker als Operator-Oberfläche gebaut.

Zuletzt wurden unter anderem verbessert:

- klarere Operator-Entscheidungsoberflächen im Cockpit
- ehrlichere Bundesland-Semantik in Karten und Regionenlisten
- sauberere Trennung von Forecast, Truth, Unsicherheit und Ranking-Signalen
- Dark-Mode-Architektur über semantische Tokens statt fragile Überschreibungen
- Accessibility für Tastatur, Fokusführung und Screenreader
- Responsive Verhalten für reale Laptop-Fenster
- konsistentere Sprache für Wahrscheinlichkeiten, Scores und Evidenzlücken
