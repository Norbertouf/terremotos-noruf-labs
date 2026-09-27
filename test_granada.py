import json
import unittest
from app import punto_en_granada, parse_entries

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

if __name__ == '__main__':
    unittest.main(verbosity=2)