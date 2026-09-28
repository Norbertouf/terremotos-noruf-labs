import asyncio
from datetime import datetime, timezone
import json, logging, math, re, sqlite3, time
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
# ---- Datos macrosismicos oficiales del IGN (Criterio B) ----
# Fichero .macro por evento: texto plano con cabecera (evid, fecha UTC, coords, profundidad,
# magnitud+tipo, intensidad maxima, localizacion oficial) y lineas "AUT/MAN <intensidad EMS
# literal> <localidad oficial>.<provincia>". Las intensidades se conservan tal cual el IGN.
MACRO_URL = 'https://www.ign.es/web/resources/sismologia/tproximos/intensidades/textos/{year}/{evid}.macro'
# Estados exactos:
# - 'valid': HTTP 200 y parser interpreta el contenido.
# - 'unavailable': HTTP 404. Significa UNICAMENTE que no hay fichero macrosismico disponible
#   en esa ruta para este evento; NUNCA equivale a "no fue sentido". No activa degradado.
# - 'parse_error': HTTP 200 pero formato no interpretable o evid no coincidente. Degradado.
# - 'transient_error': timeout/conexion/5xx. No se memoriza como resultado; se reintenta en
#   el siguiente ciclo. Degradado.
_MACRO_TTL_UNAVAILABLE_RECENT = 15 * 60   # evento < 24 h: reconsultar 404 cada 15 min (puede publicarse despues)
_MACRO_TTL_VALID = 60 * 60                # .macro valido: reconsultar cada 60 min mientras siga en el RSS
_MACRO_TTL_OLD = 60 * 60                  # evento >= 24 h: 60 min
_MACRO_RECENT = 24 * 60 * 60
_MACRO_LOCALITY_RE = re.compile(r'^(AUT|MAN)\s+([IVX]+(?:-[IVX]+)?)\s+(.+?)\.([A-Z]{1,2})\s*$')
_MACRO_CACHE = {}  # evid -> {'state': ..., 'data': {...}|None, 'checked_at': epoch}

def _macro_ttl_seconds(state, event_age_seconds):
    # Funcion pura (testeable con reloj controlado): segundos antes de reconsultar.
    if state == 'transient_error': return 0          # siempre reintenta en el siguiente ciclo
    if state == 'valid': return _MACRO_TTL_VALID
    if state in ('unavailable', 'parse_error'):
        return _MACRO_TTL_UNAVAILABLE_RECENT if event_age_seconds < _MACRO_RECENT else _MACRO_TTL_OLD
    return 0

def _macro_year(event_date_iso):
    # Ano del fichero .macro: se toma de la fecha oficial del evento (RSS), dato explicito.
    return event_date_iso[:4] if isinstance(event_date_iso, str) and len(event_date_iso) >= 4 else str(datetime.now(timezone.utc).year)

def parse_macro(texto, evid_esperado=None):
    # Parser puro y tolerante: nunca lanza; ante contenido no interpretable devuelve ok=False.
    try:
        lines = [line.rstrip() for line in texto.strip().splitlines() if line.strip()]
        if not lines: return {'ok': False}
        header = re.split(r'\s{2,}', lines[0].strip())
        # Cabecera real: [evid, 'fecha hora', 'lat lon', profundidad, mag+tipo, int_max, localizacion...]
        if len(header) < 7: return {'ok': False, 'intensity_max': None, 'felt_localities': [], 'felt_granada': False}
        evid = header[0]
        if evid_esperado and evid != evid_esperado: return {'ok': False, 'intensity_max': None, 'felt_localities': [], 'felt_granada': False}
        if not re.search(r'INTENSIDAD\s+MACROSISMICA', texto, re.I): return {'ok': False, 'intensity_max': None, 'felt_localities': [], 'felt_granada': False}
        localities, seen = [], set()
        for line in lines[1:]:
            m = _MACRO_LOCALITY_RE.match(line)
            if not m: continue
            key = line.strip()
            if key in seen: continue   # duplicados reales observados en ficheros del IGN
            seen.add(key)
            localities.append({'intensity': m.group(2), 'name': m.group(3).strip(), 'province': m.group(4)})
        return {'ok': True, 'evid': evid, 'intensity_max': header[5], 'felt_localities': localities, 'felt_granada': any(loc['province'] == 'GR' for loc in localities)}
    except Exception:
        return {'ok': False}

def _macro_event_epoch(event_date_iso):
    try: return datetime.fromisoformat(event_date_iso.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError): return 0.0

async def fetch_macro(client, evid, event_date_iso):
    # Maximo una peticion por evid y ventana TTL (cache en memoria). Un error temporal no se
    # memoriza como resultado definitivo y nunca convierte el evento en "no sentido".
    now = time.time()
    cached = _MACRO_CACHE.get(evid)
    if cached:
        event_age = max(0.0, now - _macro_event_epoch(event_date_iso))
        if now - cached['checked_at'] < _macro_ttl_seconds(cached['state'], event_age):
            return cached
    try:
        response = await client.get(MACRO_URL.format(year=_macro_year(event_date_iso), evid=evid), headers={'User-Agent': 'Terremotos-Espana/1.0'})
        if response.status_code == 404:
            result = {'state': 'unavailable', 'data': None, 'checked_at': now}
        elif response.status_code >= 500:
            return {'state': 'transient_error', 'data': None, 'checked_at': now}   # no se memoriza
        else:
            response.raise_for_status()
            parsed = parse_macro(response.text, evid_esperado=evid)
            result = {'state': 'valid' if parsed.get('ok') else 'parse_error', 'data': parsed if parsed.get('ok') else None, 'checked_at': now}
    except (httpx.HTTPError, ValueError):
        return {'state': 'transient_error', 'data': None, 'checked_at': now}       # no se memoriza
    _MACRO_CACHE[evid] = result
    return result

async def enrich_macros(events, client=None):
    # Consulta .macro para TODOS los eventos recientes (dentro y fuera de Granada), con
    # concurrencia limitada (max 4 simultaneas) para no saturar al IGN.
    # Si un evento EXTERNO termina el ciclo sin poder consultarse/interpretarse, puede haber
    # eventos sentidos ocultos: se informa macro_status='degraded' y la UI avisa discretamente.
    ids_events = [e for e in events if isinstance(e.get('id'), str) and e['id'].startswith('es')]
    if not ids_events: return 'ok'
    propio = client is None
    if propio: client = httpx.AsyncClient(timeout=12, follow_redirects=True)
    try:
        sem = asyncio.Semaphore(4)
        async def _consulta(e):
            async with sem:
                return await fetch_macro(client, e['id'], e['date'])
        results = await asyncio.gather(*(_consulta(e) for e in ids_events))
    finally:
        if propio: await client.aclose()
    for event, macro in zip(ids_events, results):
        event['macro_state'] = macro['state']
        event['intensity_max'] = macro['data'].get('intensity_max') if macro['data'] else None
        event['felt_localities'] = macro['data'].get('felt_localities') if macro['data'] else []
        event['felt_granada'] = bool(macro['data'].get('felt_granada')) if macro['data'] else False
    return 'degraded' if any(r['state'] in ('transient_error', 'parse_error') for e, r in zip(ids_events, results) if not e.get('in_granada')) else 'ok'

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
    macro_status = await enrich_macros(events)
    if events:
        with sqlite3.connect(DB) as db:
            now = datetime.now(timezone.utc).isoformat(); db.executemany('INSERT OR REPLACE INTO earthquakes VALUES (?, ?, ?)', [(e['id'], json.dumps(e), now) for e in events])
    else:
        with sqlite3.connect(DB) as db: events = [json.loads(row[0]) for row in db.execute('SELECT payload FROM earthquakes ORDER BY fetched_at DESC')]
    # Regla A+B (Criterio B):
    # - in_granada=true -> mostrar siempre (epicentro en Granada/provincia);
    # - externo con .macro 'valid' y localidad .GR -> mostrar (IGN confirma que se sintió aquí);
    # - externo con 'unavailable' -> no mostrar (sin constancia macrosísmica en la ruta);
    # - externo con 'parse_error'/'transient_error' -> no mostrar, pero macro_status='degraded'
    #   avisa de que puede haber eventos sentidos aún no mostrados. Un 404 no activa el aviso.
    def _visible(e):
        if e.get('in_granada'): return True
        if e.get('macro_state') == 'valid' and e.get('felt_granada'): return True
        return False
    filtered = [e for e in events if _visible(e) and e['magnitude'] >= min_magnitude and (not date_from or e['date'][:10] >= date_from) and (not date_to or e['date'][:10] <= date_to)]
    if location: filtered = [e for e in filtered if location.lower() in e.get('location', '').lower()]
    return {'events': filtered, 'status': status, 'macro_status': macro_status, 'updated': datetime.now(timezone.utc).isoformat()}
