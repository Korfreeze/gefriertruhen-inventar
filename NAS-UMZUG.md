# Gefriertruhen-App auf UGREEN NAS

Diese Variante läuft ohne Benutzeranmeldung vollständig auf dem NAS. Render und Supabase bleiben bis zum erfolgreichen Abschluss unverändert aktiv.

## Bestandteile

- App: FastAPI und PWA
- Datenbank: PostgreSQL 17
- Port: `8787`
- persistente Daten: `nas-data/postgres`

## 1. Datensicherung aus der Cloud

Nach Veröffentlichung dieser Version in der bisherigen Render-App anmelden und auf **Datensicherung** klicken. Die Datei `Gefriertruhen-Backup-YYYY-MM-DD.json` sicher aufbewahren.

## 2. Projekt auf das NAS übertragen

Das GitHub-Projekt per SSH auf das NAS klonen oder als ZIP in einen gemeinsamen NAS-Ordner kopieren und entpacken.

## 3. NAS-Konfiguration erstellen

```bash
cp .env.nas.example .env.nas
```

In `.env.nas` beide Vorkommen des Beispielpassworts durch dasselbe lange, zufällige Passwort ersetzen. Die Datei niemals bei GitHub hochladen.

## 4. Container starten

```bash
docker compose -f docker-compose.nas.yml up -d --build
docker compose -f docker-compose.nas.yml ps
```

Die App ist anschließend vorläufig unter `http://NAS-IP:8787` erreichbar.

## 5. Vorhandene Daten importieren

Die JSON-Datei als `backup.json` in den Ordner `migration` kopieren und dann importieren:

```bash
docker compose -f docker-compose.nas.yml run --rm app python scripts/import_backup.py /migration/backup.json
```

Der Import funktioniert zum Schutz vorhandener Daten nur bei einer leeren NAS-Datenbank. Nach erfolgreichem Import die JSON-Datei aus dem Ordner `migration` an einen sicheren Backup-Ort verschieben.

## 6. Test

- Truhe, Fächer und alle Lebensmittel vollständig vorhanden
- Mengenänderung und Einkaufsliste funktionieren
- PDF-Export und Barcode-Suche funktionieren
- Zugriff von einem zweiten Gerät funktioniert

Der Kamera-Scanner und die Installation als PWA werden erst nach Einrichtung von HTTPS zuverlässig funktionieren.

## Datenbanksicherung

```bash
docker compose -f docker-compose.nas.yml exec -T database pg_dump -U gefriertruhe -d gefriertruhe > gefriertruhe-backup.sql
```
