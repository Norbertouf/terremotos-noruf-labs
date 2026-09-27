import asyncio
import json
import time
import unittest
from unittest import mock

import app as appmod
from app import punto_en_granada, parse_entries, parse_macro, _macro_ttl_seconds, fetch_macro, MACRO_URL

# Ciudades: coordenadas de centro de municipio. Esperas verificadas contra la geometría
# provincial oficial del IGN (AU_ADMINISTRATIVEUNIT_34011800000, ver granada_polygon.json).
CIUDADES = [
    ('Granada capital', 37.1773, -3.5986, True),
    ('Huéscar', 37.8033, -2.8457, True),
    ('Motril', 36.7463, -3.5205, True),
    ('Almuñécar', 36.7348, -3.6916, True),
    ('Puebla de Don Fadrique', 37.8833, -2.4417, True),
    ('Almería capital', 36.8340, -2.4637, False),
    ('Adra (Almería)', 36.7477, -3.0193, False),
    ('Jaén capital', 37.7796, -3.7849, False),
    ('Alcalá la Real (Jaén)', 37.4604, -3.8580, False),
    ('Málaga capital', 36.7213, -4.4214, False),
    ('Antequera (Málaga)', 37.0194, -4.5614, False),
]

def rss_entry(location, lat, lon, evid):
    return {
        'title': f'-Info.terremoto: 27/09/2026 10:24:57',
        'summary': f'Se ha producido un terremoto de magnitud 2.9 en {location} en la fecha 27/09/2026 10:24:57 en la siguiente localización: {lat},{lon}',
        'geo_lat': str(lat), 'geo_long': str(lon),
        'link': f'http://www.ign.es/web/ign/portal/sis-catalogo-terremotos/-/catalogo-terremotos/detailTerremoto?evid={evid}',
        'id': f'http://www.ign.es/web/ign/portal/sis-catalogo-terremotos/-/catalogo-terremotos/detailTerremoto?evid={evid}',
    }

class TestProcedencia(unittest.TestCase):
    def test_metadatos_oficiales(self):
        with open('granada_polygon.json', encoding='utf-8') as fh:
            doc = json.load(fh)
        p = doc['procedencia']
        self.assertEqual(p['identificador'], 'AU_ADMINISTRATIVEUNIT_34011800000')
        self.assertEqual(p['nationalLevelName'], 'Provincia')
        self.assertEqual(p['nombre'], 'Granada')
        self.assertIn('EPSG:4258', p['srs'])
        self.assertIn('lat', p['orden_coordenadas'])
        self.assertEqual(len(doc['poligonos']), 2)

class TestPuntoEnGranada(unittest.TestCase):
    def test_ciudades_dentro_y_fuera(self):
        for nombre, lat, lon, esperado in CIUDADES:
            with self.subTest(ciudad=nombre):
                self.assertEqual(punto_en_granada(lat, lon), esperado, nombre)

    def test_entradas_invalidas(self):
        self.assertFalse(punto_en_granada(None, None))
        self.assertFalse(punto_en_granada(0, 0))

class TestEventosRSS(unittest.TestCase):
    def test_huescar_gr_oficial_entrante(self):
        parsed = parse_entries([rss_entry('NE HUÉSCAR.GR', 37.8608, -2.479, 'es2026svsks')])
        self.assertTrue(parsed[0]['in_granada'])
        self.assertEqual(parsed[0]['id'], 'es2026svsks')  # evid oficial capturado

    def test_ogijares_gr_oficial_entrante(self):
        parsed = parse_entries([rss_entry('NW OGÍJARES.GR', 37.1233, -3.615, 'es2026sibbq')])
        self.assertTrue(parsed[0]['in_granada'])
        self.assertEqual(parsed[0]['id'], 'es2026sibbq')

    def test_sufijo_gr_es_senal_oficial_directa(self):
        # El sufijo .GR del nombre oficial del IGN decide por sí mismo, aunque el punto cayera fuera.
        parsed = parse_entries([rss_entry('NE HUÉSCAR.GR', 36.0, -6.0, 'es2026test01')])
        self.assertTrue(parsed[0]['in_granada'])
        # La contradicción sufijo/polígono se registra, no se oculta.
        self.assertEqual(parsed[0]['granada_senal'], 'sufijo_con_inconsistencia')

    def test_senal_consistente(self):
        parsed = parse_entries([rss_entry('NE HUÉSCAR.GR', 37.8608, -2.479, 'es2026svsks')])
        self.assertEqual(parsed[0]['granada_senal'], 'sufijo_y_poligono')

    def test_evento_solo_poligono(self):
        # Localización sin sufijo (mar) pero con coordenadas dentro de la provincia.
        parsed = parse_entries([rss_entry('SIERRA NEVADA', 37.0533, -3.3250, 'es2026test03')])
        self.assertTrue(parsed[0]['in_granada'])
        self.assertEqual(parsed[0]['granada_senal'], 'poligono')

    def test_eventos_externos_quedan_fuera(self):
        casos = [
            ('GOLFO DE CÁDIZ', 36.7611, -7.392),
            ('AZORES-CABO DE SAN VICENTE', 36.9009, -13.6129),
            ('S VILLALCAMPO.ZA', 41.4799, -6.0408),
            ('SE BENIEL.MU', 38.0500, -1.0200),
        ]
        for location, lat, lon in casos:
            with self.subTest(evento=location):
                parsed = parse_entries([rss_entry(location, lat, lon, 'es2026test02')])
                self.assertFalse(parsed[0]['in_granada'], location)

# ---- Fixtures reales capturados del IGN (solo lectura, sin red en los tests) ----
FIXTURE_SVSKS = (
    "es2026svsks   2026/09/25 23:25:28    37.8608 -2.4790    4km   2.9mbLg     2.5   NE HUESCAR.GR\n"
    "Actualizado: 26.09.2026 20:15 UTC\n"
    "INTENSIDAD MACROSISMICA (EMS) Y POBLACIONES\n"
    "EN LAS QUE SE HA SENTIDO ESTE TERREMOTO:\n\n"
    "AUT II-III HUESCAR.GR\n"
    "AUT II-III HUESCAR.GR\n"
    "AUT II GRANADA.GR\n"
)
FIXTURE_SSHJS = (
    "es2026sshjs   2026/09/24 02:26:55    40.1979 -0.8813    5km   3.4mbLg     3.0   SE LA PUEBLA DE VALVERDE.TE\n"
    "Actualizado: 25.09.2026 06:58 UTC\n"
    "INTENSIDAD MACROSISMICA (EMS) Y POBLACIONES\n"
    "EN LAS QUE SE HA SENTIDO ESTE TERREMOTO:\n\n"
    "MAN III LA PUEBLA DE VALVERDE.TE\n"
    "MAN II-III SARRION.TE\n"
    "MAN II TERUEL.TE\n"
)

class TestMacroParser(unittest.TestCase):
    def test_valido_con_gr(self):
        r = parse_macro(FIXTURE_SVSKS, evid_esperado='es2026svsks')
        self.assertTrue(r['ok'])
        self.assertEqual(r['intensity_max'], '2.5')  # valor oficial de cabecera, sin convertir
        self.assertTrue(r['felt_granada'])
        nombres = [(loc['name'], loc['province'], loc['intensity']) for loc in r['felt_localities']]
        self.assertEqual(nombres, [('HUESCAR', 'GR', 'II-III'), ('GRANADA', 'GR', 'II')])  # deduplicado

    def test_valido_sin_gr(self):
        r = parse_macro(FIXTURE_SSHJS, evid_esperado='es2026sshjs')
        self.assertTrue(r['ok'])
        self.assertFalse(r['felt_granada'])
        self.assertEqual(r['felt_localities'][0]['intensity'], 'III')
        self.assertEqual(r['felt_localities'][1]['intensity'], 'II-III')
        self.assertEqual(r['felt_localities'][2]['province'], 'TE')

    def test_intensidad_simple_y_rango(self):
        texto = FIXTURE_SSHJS.replace('MAN III LA PUEBLA', 'MAN IV LA PUEBLA').replace('MAN II-III SARRION', 'MAN III-IV SARRION')
        r = parse_macro(texto, evid_esperado='es2026sshjs')
        self.assertEqual(r['felt_localities'][0]['intensity'], 'IV')
        self.assertEqual(r['felt_localities'][1]['intensity'], 'III-IV')

    def test_malformado(self):
        self.assertFalse(parse_macro('contenido corrupto sin estructura')['ok'])
        self.assertFalse(parse_macro('')['ok'])

    def test_evid_no_coincidente(self):
        self.assertFalse(parse_macro(FIXTURE_SVSKS, evid_esperado='esOtroEvento')['ok'])

    def test_exterior_sentido_en_granada(self):
        # Cabecera exterior (.TE) pero con localidad sentida .GR: felt_granada=true.
        texto = FIXTURE_SSHJS + "AUT II GRANADA.GR\n"
        r = parse_macro(texto, evid_esperado='es2026sshjs')
        self.assertTrue(r['felt_granada'])

class TestMacroTTL(unittest.TestCase):
    def test_unavailable_reciente_y_viejo(self):
        self.assertEqual(_macro_ttl_seconds('unavailable', 2 * 3600), 15 * 60)   # <24 h: 15 min
        self.assertEqual(_macro_ttl_seconds('unavailable', 30 * 3600), 60 * 60)  # >=24 h: 60 min

    def test_valid_siempre_60min(self):
        self.assertEqual(_macro_ttl_seconds('valid', 3600), 60 * 60)
        self.assertEqual(_macro_ttl_seconds('valid', 72 * 3600), 60 * 60)

    def test_parse_error_como_unavailable(self):
        self.assertEqual(_macro_ttl_seconds('parse_error', 3600), 15 * 60)
        self.assertEqual(_macro_ttl_seconds('parse_error', 30 * 3600), 60 * 60)

    def test_transient_no_se_memoriza(self):
        self.assertEqual(_macro_ttl_seconds('transient_error', 60), 0)

class TestMacroFetch(unittest.TestCase):
    def setUp(self):
        appmod._MACRO_CACHE.clear()

    def test_404_es_unavailable_y_se_cachea(self):
        class R:
            status_code = 404
        client = mock.AsyncMock()
        client.get = mock.AsyncMock(return_value=R())
        async def escenario():
            return await fetch_macro(client, 'es2026aaaa', '2026-09-25T23:25:28+00:00')
        result = asyncio.run(escenario())
        self.assertEqual(result['state'], 'unavailable')   # .macro no disponible en la ruta
        self.assertIsNone(result['data'])                  # no afirma "no sentido"
        self.assertIn('es2026aaaa', appmod._MACRO_CACHE)   # memorizable con TTL
        client.get.assert_called_once()
        self.assertIn('/2026/', client.get.call_args.args[0])  # año de la fecha RSS, no del evid

    def test_error_red_es_transient_y_no_se_cachea(self):
        async def escenario():
            client = mock.AsyncMock()
            client.get = mock.AsyncMock(side_effect=appmod.httpx.ConnectError('red caida'))
            return await fetch_macro(client, 'es2026bbbb', '2026-09-25T23:25:28+00:00')
        result = asyncio.run(escenario())
        self.assertEqual(result['state'], 'transient_error')
        self.assertNotIn('es2026bbbb', appmod._MACRO_CACHE)  # nunca memorizado como definitivo

    def test_500_es_transient(self):
        class R:
            status_code = 500
            def raise_for_status(self): raise appmod.httpx.HTTPStatusError('500', request=None, response=None)
        async def escenario():
            client = mock.AsyncMock()
            client.get = mock.AsyncMock(return_value=R())
            return await fetch_macro(client, 'es2026cccc', '2026-09-25T23:25:28+00:00')
        result = asyncio.run(escenario())
        self.assertEqual(result['state'], 'transient_error')
        self.assertNotIn('es2026cccc', appmod._MACRO_CACHE)

    def test_cache_evita_segunda_peticion(self):
        appmod._MACRO_CACHE['es2026dddd'] = {'state': 'valid', 'data': {'ok': True, 'intensity_max': '2.5', 'felt_localities': [], 'felt_granada': False}, 'checked_at': time.time() - 60}
        client = mock.AsyncMock()
        client.get = mock.AsyncMock(side_effect=AssertionError('no debe consultarse'))
        async def escenario():
            return await fetch_macro(client, 'es2026dddd', '2026-09-25T23:25:28+00:00')
        result = asyncio.run(escenario())
        self.assertEqual(result['state'], 'valid')
        client.get.assert_not_called()

    def test_ttl_expirado_reconsulta(self):
        appmod._MACRO_CACHE['es2026eeee'] = {'state': 'unavailable', 'data': None, 'checked_at': time.time() - 16 * 60}
        class R:
            status_code = 404
        client = mock.AsyncMock()
        client.get = mock.AsyncMock(return_value=R())
        async def escenario():
            return await fetch_macro(client, 'es2026eeee', '2026-09-27T10:00:00+00:00')  # evento reciente (<24 h)
        result = asyncio.run(escenario())
        client.get.assert_called_once()  # TTL 15 min superado -> reconsulta
        self.assertEqual(result['state'], 'unavailable')

    def test_malformado_200_es_parse_error(self):
        class R:
            status_code = 200
            text = 'pagina rota sin estructura'
            content = b'pagina rota sin estructura'
            def raise_for_status(self): pass
        async def escenario():
            client = mock.AsyncMock()
            client.get = mock.AsyncMock(return_value=R())
            return await fetch_macro(client, 'es2026ffff', '2026-09-25T23:25:28+00:00')
        result = asyncio.run(escenario())
        self.assertEqual(result['state'], 'parse_error')

class TestReglaAB(unittest.TestCase):
    def _visible(self, e):
        # Misma regla que el endpoint (unitarizada).
        if e.get('in_granada'): return True
        if e.get('macro_state') == 'valid' and e.get('felt_granada'): return True
        return False

    def test_matriz_visible(self):
        self.assertTrue(self._visible({'in_granada': True}))                                  # interno siempre
        self.assertTrue(self._visible({'in_granada': False, 'macro_state': 'valid', 'felt_granada': True}))   # externo sentido en GR
        self.assertFalse(self._visible({'in_granada': False, 'macro_state': 'valid', 'felt_granada': False})) # sentido fuera
        self.assertFalse(self._visible({'in_granada': False, 'macro_state': 'unavailable', 'felt_granada': False}))    # sin constancia
        self.assertFalse(self._visible({'in_granada': False, 'macro_state': 'transient_error', 'felt_granada': False})) # fallo temporal
        self.assertFalse(self._visible({'in_granada': False, 'macro_state': 'parse_error', 'felt_granada': False}))     # no interpretable

    def test_timeout_es_transient(self):
        async def escenario():
            client = mock.AsyncMock()
            client.get = mock.AsyncMock(side_effect=appmod.httpx.ReadTimeout('timeout'))
            return await fetch_macro(client, 'es2026gggg', '2026-09-25T23:25:28+00:00')
        result = asyncio.run(escenario())
        self.assertEqual(result['state'], 'transient_error')
        self.assertNotIn('es2026gggg', appmod._MACRO_CACHE)

    def test_concurrencia_real_max_4(self):
        class ClienteLento:
            def __init__(self):
                self.activos = 0; self.max_activos = 0
            async def get(self, url, headers=None):
                self.activos += 1
                self.max_activos = max(self.max_activos, self.activos)
                await asyncio.sleep(0.02)
                self.activos -= 1
                class R:
                    status_code = 404
                return R()
        cliente = ClienteLento()
        eventos = [{'id': f'es2026u{i:02d}x', 'date': '2026-09-27T10:00:00+00:00', 'in_granada': False} for i in range(24)]
        macro_status = asyncio.run(appmod.enrich_macros(eventos, client=cliente))
        self.assertEqual(macro_status, 'ok')
        self.assertLessEqual(cliente.max_activos, 4)   # concurrencia limitada
        self.assertGreater(cliente.max_activos, 1)     # y efectivamente concurrente
        self.assertTrue(all(e['macro_state'] == 'unavailable' for e in eventos))

if __name__ == '__main__':
    unittest.main(verbosity=2)