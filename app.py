from datetime import datetime, timezone
import json, logging, math, re, sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
import feedparser, httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
ROOT = Path(__file__).parent; DB = ROOT / 'earthquakes.sqlite3'
FEEDS = ['https://www.ign.es/ign/RssTools/sismologia.xml']
EMSC_FEED = 'https://www.seismicportal.eu/fdsnws/event/1/query?format=xml&limit=200&minlat=26&maxlat=45&minlon=-20&maxlon=6'
# Geometría provincial oficial de Granada (IGN/BDDAE), descargada una vez del WFS INSPIRE del IGN.
# Ver granada_polygon.json: cada punto es [lat, lon], en grados y en ese orden (orden nativo de EPSG:4258).
_GRANADA_POLY = json.loads((ROOT / 'granada_polygon.json').read_text(encoding='utf-8'))
_GRANADA_RINGS = [(_pol['exterior'], _pol.get('interiors', [])) for _pol in _GRANADA_POLY['poligonos']]
def _pip(lat, lon, ring):
    inside = False; j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]; yj, xj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi): inside = not inside
        j = i
    return inside
def punto_en_granada(lat, lon):
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)): return False
    for exterior, holes in _GRANADA_RINGS:
        if _pip(lat, lon, exterior) and not any(_pip(lat, lon, hole) for hole in holes): return True
    return False
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
        evid_match = re.search(r'evid=([^&\s<>"]+)', entry.get('link', '') or entry.get('id', '') or '')
        evid = evid_match.group(1) if evid_match else ''
        # Clasificación del epicentro: sufijo oficial .GR del nombre del IGN, o punto dentro de la
        # geometría provincial oficial (IGN/BDDAE). in_granada solo afirma dónde está el epicentro;
        # no afirma si el terremoto se sintió (eso corresponde a la fase de datos macrosísmicos).
        # Clasificación del epicentro: sufijo oficial .GR del nombre del IGN, o punto dentro de la
        # geometría provincial oficial (IGN/BDDAE). in_granada solo afirma dónde está el epicentro;
        # no afirma si el terremoto se sintió (eso corresponde a la fase de datos macrosísmicos).
        # Si el sufijo .GR y el punto oficial se contradicen, se deja constancia en granada_senal
        # y en el log; no se oculta la inconsistencia ni se presenta como certeza falsa.
        con_sufijo = location.upper().endswith('.GR')
        dentro_poligono = punto_en_granada(coords[0], coords[1])
        if con_sufijo and dentro_poligono: granada_senal = 'sufijo_y_poligono'
        elif con_sufijo:
            granada_senal = 'sufijo_con_inconsistencia'
            logging.warning('IGN: sufijo .GR fuera del polígono provincial: %s en %s,%s (evid=%s)', location, coords[0], coords[1], evid or 'sin evid')
        elif dentro_poligono: granada_senal = 'poligono'
        else: granada_senal = 'fuera'
        in_granada = con_sufijo or dentro_poligono
        result.append({'id': evid or entry.get('id', entry.get('link', text)), 'date': event_date, 'location': location, 'in_granada': in_granada, 'granada_senal': granada_senal, 'magnitude': number(magnitude_match.group(1)) if magnitude_match else 0, 'depth': None, 'duration': None, 'wave_type': None, 'lat': coords[0], 'lon': coords[1]})
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
def index(): return FileResponse(ROOT / 'templates' / 'index.html')
@app.get('/api/earthquakes')
async def earthquakes(min_magnitude: float = Query(0, ge=0, le=10), location: str = '', date_from: str = '', date_to: str = ''):
    events, status = await fetch_ign()
    events = enrich_depth(events, await fetch_emsc_depth()) if events else events
    if events:
        with sqlite3.connect(DB) as db:
            now = datetime.now(timezone.utc).isoformat(); db.executemany('INSERT OR REPLACE INTO earthquakes VALUES (?, ?, ?)', [(e['id'], json.dumps(e), now) for e in events])
    else:
        with sqlite3.connect(DB) as db: events = [json.loads(row[0]) for row in db.execute('SELECT payload FROM earthquakes ORDER BY fetched_at DESC')]
    # Criterio A: solo eventos con epicentro dentro de Granada/provincia (señal oficial .GR o
    # geometría provincial IGN). La ausencia de datos macrosísmicos no afirma aquí nada sobre
    # si un terremoto se sintió; el criterio B (sentidos en Granada) es la fase siguiente.
    filtered = [e for e in events if e.get('in_granada') and e['magnitude'] >= min_magnitude and (not date_from or e['date'][:10] >= date_from) and (not date_to or e['date'][:10] <= date_to)]
    if location: filtered = [e for e in filtered if location.lower() in e.get('location', '').lower()]
    return {'events': filtered, 'status': status, 'updated': datetime.now(timezone.utc).isoformat()}
