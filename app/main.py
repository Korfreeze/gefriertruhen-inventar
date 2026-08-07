from pathlib import Path
from typing import Any
import os
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_ANON_KEY", "")
app = FastAPI(title="Gefriertruhen-Inventar", version="0.1.0")

class Item(BaseModel):
    freezer_id: int
    location_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    category: str | None = None
    quantity: float = Field(default=1, ge=0)
    unit: str = "Stück"
    frozen_at: str | None = None
    best_before: str | None = None
    barcode: str | None = None
    notes: str | None = None

class ItemUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    location_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    frozen_at: str | None = None
    barcode: str | None = Field(default=None, max_length=100)

class ShoppingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(default=1, ge=0)
    unit: str = Field(default="Stück", min_length=1, max_length=30)
    source_item_id: int | None = None

class ShoppingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    checked: bool | None = None

class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = None

def headers(auth: str | None):
    if not URL or not KEY:
        raise HTTPException(503, "Bitte zuerst die .env-Datei einrichten.")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(401, "Bitte zuerst anmelden.")
    return {"apikey": KEY, "Authorization": auth, "Content-Type": "application/json"}

async def db(method: str, table: str, auth: str | None, *, params=None, body=None, prefer=None) -> Any:
    h = headers(auth)
    if prefer: h["Prefer"] = prefer
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.request(method, f"{URL}/rest/v1/{table}", headers=h, params=params, json=body)
    if r.status_code >= 400:
        try: detail = r.json().get("message", r.text)
        except ValueError: detail = r.text
        raise HTTPException(r.status_code, detail or "Datenbankfehler")
    return r.json() if r.content else None

@app.get("/api/config")
def config():
    if not URL or not KEY: raise HTTPException(503, "Bitte zuerst die .env-Datei einrichten.")
    return {"supabaseUrl": URL, "supabaseAnonKey": KEY}

@app.get("/api/health")
def health(): return {"status": "ok", "supabase": "configured" if URL and KEY else "missing"}

@app.get("/api/freezers")
async def freezers(authorization: str | None = Header(None)):
    return await db("GET", "freezers", authorization, params={"select":"*","order":"created_at.asc"})

@app.post("/api/freezers", status_code=201)
async def add_freezer(payload: dict[str,str], authorization: str | None = Header(None)):
    name = payload.get("name", "").strip()
    if not name: raise HTTPException(422, "Bitte einen Namen eingeben.")
    return await db("POST", "freezers", authorization, body={"name":name}, prefer="return=representation")

@app.get("/api/locations")
async def locations(freezer_id: int = Query(...), authorization: str | None = Header(None)):
    return await db("GET", "locations", authorization, params={"select":"*","freezer_id":f"eq.{freezer_id}","order":"sort_order.asc"})

@app.post("/api/locations", status_code=201)
async def add_location(payload: dict[str, Any], authorization: str | None = Header(None)):
    name = str(payload.get("name", "")).strip()
    freezer_id = payload.get("freezer_id")
    if not name or not freezer_id:
        raise HTTPException(422, "Name und Gefriertruhe werden benötigt.")
    return await db("POST", "locations", authorization, body={"name": name, "freezer_id": freezer_id}, prefer="return=representation")

@app.patch("/api/locations/{location_id}")
async def update_location(location_id: int, payload: LocationUpdate, authorization: str | None = Header(None)):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Es wurde keine Änderung übergeben.")
    return await db("PATCH", "locations", authorization, params={"id": f"eq.{location_id}"}, body=changes, prefer="return=representation")

@app.delete("/api/locations/{location_id}", status_code=204)
async def delete_location(location_id: int, authorization: str | None = Header(None)):
    await db("DELETE", "locations", authorization, params={"id": f"eq.{location_id}"})

@app.get("/api/items")
async def items(freezer_id: int = Query(...), authorization: str | None = Header(None)):
    return await db("GET", "items", authorization, params={"select":"*,locations(name)","freezer_id":f"eq.{freezer_id}","order":"name.asc"})

@app.post("/api/items", status_code=201)
async def add_item(item: Item, authorization: str | None = Header(None)):
    return await db("POST", "items", authorization, body=item.model_dump(exclude_none=True), prefer="return=representation")

@app.patch("/api/items/{item_id}")
async def update_item(item_id: int, payload: ItemUpdate, authorization: str | None = Header(None)):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Es wurde keine Änderung übergeben.")
    return await db("PATCH", "items", authorization, params={"id":f"eq.{item_id}"}, body=changes, prefer="return=representation")

@app.delete("/api/items/{item_id}", status_code=204)
async def delete_item(item_id: int, authorization: str | None = Header(None)):
    await db("DELETE", "items", authorization, params={"id":f"eq.{item_id}"})

@app.get("/api/products/{barcode}")
async def product_by_barcode(barcode: str, authorization: str | None = Header(None)):
    headers(authorization)
    code = "".join(character for character in barcode if character.isdigit())
    if not code:
        raise HTTPException(422, "Der Barcode enthält keine Ziffern.")
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(
            f"https://world.openfoodfacts.org/api/v3/product/{code}",
            params={"fields": "product_name_de,product_name,categories_tags"},
            headers={"User-Agent": "GefriertruhenInventar/0.1 (https://gefriertruhen-inventar.onrender.com)"},
        )
    if response.status_code == 404:
        return {"found": False, "barcode": code}
    if response.status_code >= 400:
        raise HTTPException(502, "Die Produktdatenbank ist momentan nicht erreichbar.")
    product = response.json().get("product", {})
    categories = product.get("categories_tags") or []
    category = categories[0].split(":")[-1].replace("-", " ").title() if categories else None
    return {
        "found": bool(product),
        "barcode": code,
        "name": product.get("product_name_de") or product.get("product_name"),
        "category": category,
    }

@app.get("/api/shopping-list")
async def get_shopping_list(authorization: str | None = Header(None)):
    return await db("GET", "shopping_list", authorization, params={"select": "*", "order": "checked.asc,created_at.desc"})

@app.post("/api/shopping-list", status_code=201)
async def add_shopping_item(payload: ShoppingCreate, authorization: str | None = Header(None)):
    return await db("POST", "shopping_list", authorization, body=payload.model_dump(exclude_none=True), prefer="return=representation")

@app.patch("/api/shopping-list/{entry_id}")
async def update_shopping_item(entry_id: int, payload: ShoppingUpdate, authorization: str | None = Header(None)):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Es wurde keine Änderung übergeben.")
    return await db("PATCH", "shopping_list", authorization, params={"id": f"eq.{entry_id}"}, body=changes, prefer="return=representation")

@app.delete("/api/shopping-list/{entry_id}", status_code=204)
async def delete_shopping_item(entry_id: int, authorization: str | None = Header(None)):
    await db("DELETE", "shopping_list", authorization, params={"id": f"eq.{entry_id}"})

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
@app.get("/", include_in_schema=False)
def index(): return FileResponse(ROOT / "static" / "index.html")
