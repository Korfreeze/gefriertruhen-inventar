# Gefriertruhen-Inventar

Installierbare PWA mit FastAPI, Supabase-Anmeldung und Live-Synchronisierung.

## 1. Supabase eintragen

Im Supabase-Dashboard unter **Project Settings → API** findest du Projekt-URL und öffentlichen `anon`-Schlüssel. Kopiere `.env.example` nach `.env` und trage beide Werte ein. Niemals den geheimen `service_role`-Schlüssel verwenden.

## 2. Entwicklungsumgebung (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3. Starten

```powershell
uvicorn app.main:app --reload
```

Öffne <http://127.0.0.1:8000>. Die API-Dokumentation liegt unter <http://127.0.0.1:8000/docs>.

## 4. Ausprobieren

Lege über **Neues Konto anlegen** einen Benutzer an. Falls Supabase E-Mail-Bestätigung verlangt, bestätige zuerst die Nachricht. Lege danach eine Gefriertruhe und Lebensmittel an. Öffne die App in zwei Fenstern: Mengenänderungen erscheinen live in beiden.

## Struktur

```text
app/main.py         FastAPI und geschützte Datenbank-API
static/index.html   Oberfläche
static/app.js       Anmeldung, Bedienung und Realtime
static/styles.css   mobile Gestaltung
static/manifest...  PWA-Konfiguration
static/sw.js        Offline-Cache der Oberfläche
```

Nächste Schritte: Fachverwaltung, Haushalte, Barcode-Scanner, HTTPS-Bereitstellung und NAS-Backup.
