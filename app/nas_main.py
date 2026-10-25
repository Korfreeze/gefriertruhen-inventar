from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import asyncio
import os

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.main import Item, ItemUpdate, LocationUpdate, ShoppingCreate, ShoppingUpdate, build_inventory_pdf

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = os.environ["DATABASE_URL"]
app = FastAPI(title="Gefriertruhen-Inventar NAS", version="1.0.0")

async def fetch_all(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(query, params)
            return await cursor.fetchall()

async def execute(query: str, params: tuple = (), returning: bool = True):
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(query, params)
            result = await cursor.fetchall() if returning else None
        await connection.commit()
        return result

@app.get("/api/config")
def config(): return {"localMode": True}

@app.get("/api/health")
async def health():
    await fetch_all("select 1 as ok")
    return {"status": "ok", "database": "connected", "mode": "nas"}

@app.get("/api/freezers")
async def freezers(): return await fetch_all("select * from freezers order by created_at")

@app.post("/api/freezers", status_code=201)
async def add_freezer(payload: dict[str, str]):
    name = payload.get("name", "").strip()
    if not name: raise HTTPException(422, "Bitte einen Namen eingeben.")
    return await execute("insert into freezers(name) values (%s) returning *", (name,))

@app.get("/api/locations")
async def locations(freezer_id: int = Query(...)):
    return await fetch_all("select * from locations where freezer_id=%s order by sort_order,id", (freezer_id,))

@app.post("/api/locations", status_code=201)
async def add_location(payload: dict[str, Any]):
    name, freezer_id = str(payload.get("name", "")).strip(), payload.get("freezer_id")
    if not name or not freezer_id: raise HTTPException(422, "Name und Gefriertruhe werden benötigt.")
    return await execute("insert into locations(freezer_id,name) values (%s,%s) returning *", (freezer_id, name))

@app.patch("/api/locations/{location_id}")
async def update_location(location_id: int, payload: LocationUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes: raise HTTPException(422, "Es wurde keine Änderung übergeben.")
    columns = list(changes)
    values = tuple(changes[column] for column in columns) + (location_id,)
    assignments = ",".join(f"{column}=%s" for column in columns)
    return await execute(f"update locations set {assignments} where id=%s returning *", values)

@app.delete("/api/locations/{location_id}", status_code=204)
async def delete_location(location_id: int):
    await execute("delete from locations where id=%s", (location_id,), False)

@app.get("/api/items")
async def items(freezer_id: int = Query(...)):
    rows = await fetch_all("""select i.*, l.name as location_name from items i left join locations l on l.id=i.location_id
                            where i.freezer_id=%s order by i.name""", (freezer_id,))
    for row in rows:
        row["locations"] = {"name": row.pop("location_name")} if row.get("location_name") else None
    return rows

@app.post("/api/items", status_code=201)
async def add_item(item: Item):
    data = item.model_dump(exclude_none=True)
    columns = list(data)
    placeholders = ",".join(["%s"] * len(columns))
    return await execute(f"insert into items({','.join(columns)}) values ({placeholders}) returning *", tuple(data[c] for c in columns))

@app.patch("/api/items/{item_id}")
async def update_item(item_id: int, payload: ItemUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes: raise HTTPException(422, "Es wurde keine Änderung übergeben.")
    columns = list(changes)
    values = tuple(changes[c] for c in columns) + (item_id,)
    assignments = ",".join(f"{column}=%s" for column in columns)
    return await execute(f"update items set {assignments},updated_at=now() where id=%s returning *", values)

@app.delete("/api/items/{item_id}", status_code=204)
async def delete_item(item_id: int): await execute("delete from items where id=%s", (item_id,), False)

@app.get("/api/products/{barcode}")
async def product_by_barcode(barcode: str):
    code = "".join(c for c in barcode if c.isdigit())
    if not code: raise HTTPException(422, "Der Barcode enthält keine Ziffern.")
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(f"https://world.openfoodfacts.org/api/v3/product/{code}",
            params={"fields":"product_name_de,product_name,categories_tags,image_front_small_url,image_front_url"},
            headers={"User-Agent":"GefriertruhenInventar-NAS/1.0"})
    if response.status_code == 404: return {"found": False, "barcode": code}
    if response.status_code >= 400: raise HTTPException(502, "Die Produktdatenbank ist momentan nicht erreichbar.")
    product = response.json().get("product", {})
    categories = product.get("categories_tags") or []
    return {"found": bool(product), "barcode": code,
            "name": product.get("product_name_de") or product.get("product_name"),
            "category": categories[0].split(":")[-1].replace("-", " ").title() if categories else None,
            "image_url": product.get("image_front_small_url") or product.get("image_front_url")}

@app.get("/api/shopping-list")
async def shopping(): return await fetch_all("select * from shopping_list order by checked,created_at desc")

@app.post("/api/shopping-list", status_code=201)
async def add_shopping(payload: ShoppingCreate):
    data = payload.model_dump(exclude_none=True); columns = list(data)
    return await execute(f"insert into shopping_list({','.join(columns)}) values ({','.join(['%s']*len(columns))}) returning *", tuple(data[c] for c in columns))

@app.patch("/api/shopping-list/{entry_id}")
async def update_shopping(entry_id: int, payload: ShoppingUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes: raise HTTPException(422, "Es wurde keine Änderung übergeben.")
    columns=list(changes); values=tuple(changes[c] for c in columns)+(entry_id,)
    return await execute(f"update shopping_list set {','.join(f'{c}=%s' for c in columns)},updated_at=now() where id=%s returning *", values)

@app.delete("/api/shopping-list/{entry_id}", status_code=204)
async def delete_shopping(entry_id: int): await execute("delete from shopping_list where id=%s", (entry_id,), False)

async def inventory_pdf(freezer_id: int):
    freezer = await fetch_all("select * from freezers where id=%s", (freezer_id,))
    if not freezer: raise HTTPException(404, "Gefriertruhe nicht gefunden.")
    inventory = await items(freezer_id)
    images: dict[int, bytes] = {}; semaphore = asyncio.Semaphore(5)
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        async def load(item):
            parsed=urlparse(str(item.get("image_url") or ""))
            if parsed.scheme != "https" or not parsed.hostname or not (parsed.hostname == "openfoodfacts.org" or parsed.hostname.endswith(".openfoodfacts.org")): return
            try:
                async with semaphore:
                    response=await client.get(item["image_url"])
                    if response.is_success and response.headers.get("content-type","").startswith("image/") and len(response.content)<=5_000_000: images[int(item["id"])]=response.content
            except httpx.HTTPError: pass
        await asyncio.gather(*(load(item) for item in inventory))
    name=str(freezer[0]["name"]); pdf=build_inventory_pdf(name,inventory,images)
    safe="".join(c if c.isalnum() else "-" for c in name).strip("-") or "Gefriertruhe"
    return StreamingResponse(pdf,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="Inventar-{safe}-{date.today().isoformat()}.pdf"'})

app.get("/api/export/inventory.pdf")(inventory_pdf)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
@app.get("/", include_in_schema=False)
def index(): return FileResponse(ROOT / "static" / "index.html")
