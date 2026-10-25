from pathlib import Path
from typing import Any
from datetime import date, datetime
from html import escape
from io import BytesIO
from urllib.parse import urlparse
import asyncio
import os
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    image_url: str | None = None
    notes: str | None = None

class ItemUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    location_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    frozen_at: str | None = None
    best_before: str | None = None
    barcode: str | None = Field(default=None, max_length=100)
    image_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)

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
    return {"localMode": False, "supabaseUrl": URL, "supabaseAnonKey": KEY}

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

@app.get("/api/export/backup.json")
async def export_backup(authorization: str | None = Header(None)):
    backup = {
        "format": "gefriertruhen-inventar-backup-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "freezers": await db("GET", "freezers", authorization, params={"select": "*", "order": "id.asc"}),
        "locations": await db("GET", "locations", authorization, params={"select": "*", "order": "id.asc"}),
        "items": await db("GET", "items", authorization, params={"select": "*", "order": "id.asc"}),
        "shopping_list": await db("GET", "shopping_list", authorization, params={"select": "*", "order": "id.asc"}),
    }
    filename = f"Gefriertruhen-Backup-{date.today().isoformat()}.json"
    return JSONResponse(backup, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

def _display_date(value: str | None) -> str:
    if not value:
        return "-"
    try:
        return date.fromisoformat(value[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return value

def _display_quantity(value: Any) -> str:
    number = float(value or 0)
    return f"{number:g}".replace(".", ",")

def build_inventory_pdf(freezer_name: str, inventory: list[dict[str, Any]], images: dict[int, bytes]) -> BytesIO:
    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    if "Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Vera", str(font_dir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("Vera-Bold", str(font_dir / "VeraBd.ttf")))
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm,
                                 topMargin=17*mm, bottomMargin=16*mm,
                                 title=f"Inventar - {freezer_name}", author="Gefriertruhen-Inventar")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("InventoryTitle", parent=styles["Title"], fontName="Vera-Bold",
                           fontSize=22, leading=26, textColor=colors.HexColor("#084f4c"), spaceAfter=4*mm)
    meta = ParagraphStyle("InventoryMeta", parent=styles["BodyText"], fontName="Vera", fontSize=9, leading=12,
                          textColor=colors.HexColor("#66807e"), spaceAfter=6*mm)
    name_style = ParagraphStyle("ItemName", parent=styles["Heading3"], fontName="Vera-Bold",
                                fontSize=12, leading=14, textColor=colors.HexColor("#183332"), spaceAfter=1.5*mm)
    body = ParagraphStyle("ItemBody", parent=styles["BodyText"], fontName="Vera", fontSize=8.5, leading=11,
                          textColor=colors.HexColor("#324f4d"))
    note = ParagraphStyle("ItemNote", parent=body, textColor=colors.HexColor("#66807e"), spaceBefore=1.5*mm)
    story = [Paragraph(f"Inventar: {escape(freezer_name)}", title),
             Paragraph(f"Stand: {datetime.now().strftime('%d.%m.%Y, %H:%M Uhr')} &nbsp;&nbsp;|&nbsp;&nbsp; {len(inventory)} Positionen", meta)]
    if not inventory:
        story.append(Paragraph("In dieser Gefriertruhe sind derzeit keine Lebensmittel eingetragen.", body))
    for item in inventory:
        item_id = int(item.get("id", 0))
        image_data = images.get(item_id)
        if image_data:
            try:
                picture = Image(BytesIO(image_data), width=25*mm, height=25*mm, kind="proportional")
            except Exception:
                picture = Paragraph("Kein Bild", ParagraphStyle("NoImage", parent=body, alignment=TA_CENTER))
        else:
            picture = Paragraph("Kein Bild", ParagraphStyle("NoImage", parent=body, alignment=TA_CENTER,
                                                               textColor=colors.HexColor("#8ba09e")))
        location = (item.get("locations") or {}).get("name") or "Ohne Fach"
        details = (
            f"<b>{escape(str(item.get('category') or 'Ohne Kategorie'))}</b><br/>"
            f"Menge: {_display_quantity(item.get('quantity'))} {escape(str(item.get('unit') or ''))}<br/>"
            f"Lagerort: {escape(str(location))}<br/>"
            f"Eingefroren: {_display_date(item.get('frozen_at'))} &nbsp;&nbsp; MHD: {_display_date(item.get('best_before'))}"
        )
        text = [Paragraph(escape(str(item.get("name") or "Ohne Name")), name_style), Paragraph(details, body)]
        if item.get("notes"):
            text.append(Paragraph(f"Notiz: {escape(str(item['notes'])).replace(chr(10), '<br/>')}", note))
        card = Table([[picture, text]], colWidths=[31*mm, 144*mm], hAlign="LEFT")
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dce8e6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4*mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4*mm),
            ("TOPPADDING", (0, 0), (-1, -1), 3*mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
        ]))
        story.extend([KeepTogether([card]), Spacer(1, 3*mm)])
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Vera", 8)
        canvas.setFillColor(colors.HexColor("#66807e"))
        canvas.drawCentredString(A4[0]/2, 8*mm, f"Seite {doc.page}")
        canvas.restoreState()
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output

@app.get("/api/export/inventory.pdf")
async def export_inventory_pdf(freezer_id: int = Query(...), authorization: str | None = Header(None)):
    freezer_rows = await db("GET", "freezers", authorization, params={"select": "id,name", "id": f"eq.{freezer_id}", "limit": 1})
    if not freezer_rows:
        raise HTTPException(404, "Gefriertruhe nicht gefunden.")
    inventory = await db("GET", "items", authorization, params={"select": "*,locations(name)", "freezer_id": f"eq.{freezer_id}", "order": "name.asc"})
    image_bytes: dict[int, bytes] = {}
    semaphore = asyncio.Semaphore(5)
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        async def load_image(item: dict[str, Any]):
            image_url = item.get("image_url")
            parsed = urlparse(str(image_url or ""))
            if parsed.scheme != "https" or not parsed.hostname or not (parsed.hostname == "openfoodfacts.org" or parsed.hostname.endswith(".openfoodfacts.org")):
                return
            try:
                async with semaphore:
                    response = await client.get(str(image_url))
                    if response.is_success and response.headers.get("content-type", "").startswith("image/") and len(response.content) <= 5_000_000:
                        image_bytes[int(item["id"])] = response.content
            except httpx.HTTPError:
                pass
        await asyncio.gather(*(load_image(item) for item in inventory))
    freezer_name = str(freezer_rows[0]["name"])
    safe_name = "".join(character if character.isalnum() else "-" for character in freezer_name).strip("-") or "Gefriertruhe"
    pdf = build_inventory_pdf(freezer_name, inventory, image_bytes)
    filename = f"Inventar-{safe_name}-{date.today().isoformat()}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

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
            params={"fields": "product_name_de,product_name,categories_tags,image_front_small_url,image_front_url"},
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
        "image_url": product.get("image_front_small_url") or product.get("image_front_url"),
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
