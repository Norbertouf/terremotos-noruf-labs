from datetime import datetime, timezone
import json, math, re, sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
import feedparser, httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
ROOT = Path(__file__).parent; DB = ROOT / 'earthquakes.sqlite3'
FEEDS = ['https://www.ign.es/ign/RssTools/sismologia.xml']
EMSC_FEED = 'https://www.seismicportal.eu/fdsnws/event/1/query?format=xml&limit=200&minlat=26&maxlat=45&minlon=-20&maxlon=6'
PROVINCE_CODES = {'AL': 'Almería', 'AV': 'Ávila', 'B': 'Barcelona', 'BA': 'Badajoz', 'BI': 'Bizkaia', 'BU': 'Burgos', 'C': 'A Coruña', 'CA': 'Cádiz', 'CC': 'Cáceres', 'CO': 'Córdoba', 'CR': 'Ciudad Real', 'CS': 'Castellón', 'CU': 'Cuenca', 'GC': 'Las Palmas', 'GI': 'Girona', 'GR': 'Granada', 'GU': 'Guadalajara', 'H': 'Huelva', 'HU': 'Huesca', 'J': 'Jaén', 'L': 'Lleida', 'LE': 'León', 'LO': 'La Rioja', 'LU': 'Lugo', 'M': 'Madrid', 'MA': 'Málaga', 'MU': 'Murcia', 'NA': 'Navarra', 'O': 'Asturias', 'OR': 'Ourense', 'P': 'Palencia', 'PM': 'Baleares', 'PO': 'Pontevedra', 'S': 'Cantabria', 'SA': 'Salamanca', 'SE': 'Sevilla', 'SG': 'Segovia', 'SO': 'Soria', 'SS': 'Gipuzkoa', 'T': 'Tarragona', 'TE': 'Teruel', 'TF': 'Santa Cruz de Tenerife', 'TO': 'Toledo', 'V': 'Valencia', 'VA': 'Valladolid', 'VI': 'Álava', 'Z': 'Zaragoza', 'ZA': 'Zamora'}
app = FastAPI(title='Terremotos España'); app.mount('/static', StaticFiles(directory=ROOT), name='static')
def number(value, default=0.0):
    try: return float(str(value).replace(',', '.'))
    except (TypeError, ValueError): return default
def parse_entries(entries):
    result = []
    for entry in entries:
        description = entry.get('summary', '')
        text = f"{entry.get('title', '')} {description}"; coords = [number(entry.get('geo_lat')), number(entry.get('geo_long'))]
        if not all(coords):
            found = re.findall(r'-?\d+\.\d+', text); coords = [number(found[-2]), number(found[-1])] if len(found) >= 2 else [0, 0]
        if not all(coords): continue
        magnitude_match = re.search(r'magnitud\s+([0-9]+(?:[.,][0-9]+)?)', description, re.I)
        date_match = re.search(r'en la fecha\s+(\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}:\d{2})', description, re.I)
        location_match = re.search(r'magnitud\s+[0-9.,]+\s+en\s+(.+?)\s+en la fecha', description, re.I | re.S)
        event_date = datetime.strptime(date_match.group(1), '%d/%m/%Y %H:%M:%S').replace(tzinfo=timezone.utc).isoformat() if date_match else datetime.now(timezone.utc).isoformat()
        location = location_match.group(1).strip() if location_match else entry.get('title', 'Evento sísmico')
        code = re.search(r'\.([A-Z]{1,2})$', location)
        province = PROVINCE_CODES.get(code.group(1)) if code else ('Canarias' if 'CANARI' in location.upper() else ('Baleares' if 'BALEAR' in location.upper() else ''))
        result.append({'id': entry.get('id', entry.get('link', text)), 'date': event_date, 'location': location, 'province': province, 'magnitude': number(magnitude_match.group(1)) if magnitude_match else 0, 'depth': None, 'duration': None, 'wave_type': None, 'lat': coords[0], 'lon': coords[1]})
    return result

async def fetch_emsc_depth():
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            response = await client.get(EMSC_FEED, headers={'User-Agent': 'Terremotos-Espana/1.0'}); response.raise_for_status()
            root = ET.fromstring(response.content); result = []
            for event in root.findall('.//{*}event'):
                origin = event.find('.//{*}origin'); magnitude = event.find('.//{*}magnitude'); description = event.find('.//{*}description/{*}text')
                if origin is None: continue
                value = lambda path: (origin.findtext(path) or '')
                result.append({'date': value('{*}time/{*}value'), 'lat': number(value('{*}latitude/{*}value')), 'lon': number(value('{*}longitude/{*}value')), 'depth': number(value('{*}depth/{*}value')) / 1000, 'magnitude': number(magnitude.findtext('.//{*}value') if magnitude is not None else 0), 'wave_type': event.findtext('{*}type'), 'location': description.text.strip() if description is not None and description.text else ''})
            return result
        except (httpx.HTTPError, ET.ParseError, ValueError):
            return []

def enrich_depth(events, emsc_events):
    for event in events:
        event_date = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
        matches = [candidate for candidate in emsc_events if abs(candidate['lat'] - event['lat']) < 0.12 and abs(candidate['lon'] - event['lon']) < 0.12 and abs((datetime.fromisoformat(candidate['date'].replace('Z', '+00:00')) - event_date).total_seconds()) < 1800]
        if matches:
            candidate = min(matches, key=lambda item: abs(item['lat'] - event['lat']) + abs(item['lon'] - event['lon']))
            event['depth'] = round(candidate['depth'], 2) if candidate['depth'] > 0 else None; event['wave_type'] = candidate['wave_type']
    return events
def setup_db():
    with sqlite3.connect(DB) as db: db.execute('CREATE TABLE IF NOT EXISTS earthquakes (id TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)')
async def fetch_ign():
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for url in FEEDS:
            try:
                response = await client.get(url, headers={'User-Agent': 'Terremotos-Espana/1.0'}); response.raise_for_status(); events = parse_entries(feedparser.parse(response.content).entries)
                if events: return events, 'live'
            except (httpx.HTTPError, ValueError): pass
    return [], 'cache'
@app.on_event('startup')
def startup(): setup_db()
@app.get('/')
def index(): return FileResponse(ROOT / 'index.html')
@app.get('/api/earthquakes')
async def earthquakes(min_magnitude: float = Query(0, ge=0, le=10), location: str = '', date_from: str = '', date_to: str = ''):
    events, status = await fetch_ign()
    events = enrich_depth(events, await fetch_emsc_depth()) if events else events
    if events:
        with sqlite3.connect(DB) as db:
            now = datetime.now(timezone.utc).isoformat(); db.executemany('INSERT OR REPLACE INTO earthquakes VALUES (?, ?, ?)', [(e['id'], json.dumps(e), now) for e in events])
    else:
        with sqlite3.connect(DB) as db: events = [json.loads(row[0]) for row in db.execute('SELECT payload FROM earthquakes ORDER BY fetched_at DESC')]
    filtered = [e for e in events if e['magnitude'] >= min_magnitude and (not location or e.get('province') == location) and (not date_from or e['date'][:10] >= date_from) and (not date_to or e['date'][:10] <= date_to)]
    return {'events': filtered, 'status': status, 'updated': datetime.now(timezone.utc).isoformat()}
