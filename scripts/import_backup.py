import argparse
import json
import os
from pathlib import Path

import psycopg

TABLES = ("freezers", "locations", "items", "shopping_list")

def main():
    parser = argparse.ArgumentParser(description="Gefriertruhen-Backup in die NAS-Datenbank importieren")
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    data = json.loads(args.backup.read_text(encoding="utf-8"))
    if data.get("format") != "gefriertruhen-inventar-backup-v1":
        raise SystemExit("Unbekanntes Backup-Format. Import wurde abgebrochen.")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select exists(select 1 from freezers) or exists(select 1 from items)")
            if cursor.fetchone()[0]:
                raise SystemExit("Die NAS-Datenbank ist nicht leer. Import wurde zum Schutz vorhandener Daten abgebrochen.")
            for table in TABLES:
                for row in data.get(table, []):
                    columns = list(row)
                    values = [row[column] for column in columns]
                    cursor.execute(f"insert into {table} ({','.join(columns)}) values ({','.join(['%s'] * len(columns))})", values)
            for table in TABLES:
                cursor.execute("select pg_get_serial_sequence(%s, 'id')", (table,))
                sequence = cursor.fetchone()[0]
                if sequence:
                    cursor.execute(f"select setval(%s, coalesce((select max(id) from {table}),1), true)", (sequence,))
        connection.commit()
    print("Import erfolgreich abgeschlossen.")
    for table in TABLES:
        print(f"{table}: {len(data.get(table, []))} Einträge")

if __name__ == "__main__":
    main()
