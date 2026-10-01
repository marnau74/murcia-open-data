"""Tests del cliente de murciaturistica.es (sin red)."""

import re
from pathlib import Path

import pytest
import requests

from murcia_data.ingest.murciaturistica_client import BASE_URL, REFERER, REVISAR_ULTIMOS, MurciaturisticaClient


def test_el_cliente_reintenta_si_el_servidor_corta_la_conexion(tmp_path):
    cliente = MurciaturisticaClient(cache_dir=tmp_path)
    reintentos = cliente.session.get_adapter(BASE_URL).max_retries

    # Una conexión cortada sin respuesta (el fallo real de la ejecución de septiembre
    # de 2026) cuenta como error de lectura: se reintenta con espera exponencial.
    assert reintentos.total == 5
    assert reintentos.backoff_factor > 0
    assert reintentos.is_retry("GET", 503)


def test_el_cliente_envia_el_referer_que_exige_el_portal(tmp_path):
    cliente = MurciaturisticaClient(cache_dir=tmp_path)
    assert cliente.session.headers["Referer"] == REFERER


FIXTURE = Path(__file__).parent / "fixtures" / "murciaturistica" / "destinos_2019-07.html"


class SesionFalsa:
    """Sustituye a la sesión HTTP: cuenta las peticiones y responde con el HTML de un mes."""

    def __init__(self, contenido: bytes, falla: bool = False):
        self.contenido = contenido
        self.falla = falla
        self.peticiones = 0
        self.headers = {}

    def get(self, url, timeout):
        self.peticiones += 1
        if self.falla:
            raise requests.ConnectionError("sin red")
        respuesta = requests.Response()
        respuesta.status_code = 200
        respuesta._content = self.contenido
        return respuesta


def _cliente(tmp_path, sesion) -> MurciaturisticaClient:
    cliente = MurciaturisticaClient(cache_dir=tmp_path, pausa=0)
    cliente.session = sesion
    return cliente


def test_los_meses_antiguos_salen_de_la_cache_y_los_ultimos_se_revisan(tmp_path):
    sesion = SesionFalsa(FIXTURE.read_bytes())
    cliente = _cliente(tmp_path, sesion)

    cliente.serie(2019, 1, 2019, 12)
    assert sesion.peticiones == 12
    assert len(list(tmp_path.glob("destinos_*.html"))) == 12

    cliente.serie(2019, 1, 2019, 12)
    assert sesion.peticiones == 12 + REVISAR_ULTIMOS, "solo se vuelven a pedir los últimos meses"


def test_un_mes_sin_publicar_se_guarda_y_no_se_pide_en_cada_ejecucion_cuando_ya_es_antiguo(tmp_path):
    # Antes un mes a 0 se borraba de la caché y se volvía a pedir siempre: con la fuente parada desde 2024, cada
    # ejecución pedía todos los meses posteriores, y cada mes uno más.
    vacio = re.sub(rb">\s*[\d.,]+\s*<", b">0<", FIXTURE.read_bytes())  # la tabla de un mes sin publicar: todo a 0
    sesion = SesionFalsa(vacio)
    cliente = _cliente(tmp_path, sesion)

    cliente.serie(2025, 1, 2026, 9)
    primeras = sesion.peticiones
    cliente.serie(2025, 1, 2026, 9)

    assert sesion.peticiones - primeras == REVISAR_ULTIMOS
    assert len(list(tmp_path.glob("destinos_*.html"))) == 21, "los meses vacíos también se guardan"


def test_si_falla_la_revision_de_un_mes_ya_guardado_se_usa_la_copia(tmp_path):
    _cliente(tmp_path, SesionFalsa(FIXTURE.read_bytes())).serie(2019, 7, 2019, 7)

    tabla = _cliente(tmp_path, SesionFalsa(b"", falla=True)).serie(2019, 7, 2019, 7)

    assert tabla["viajeros_total"].notna().any()


def test_si_falla_un_mes_que_no_esta_en_la_cache_es_un_error(tmp_path):
    with pytest.raises(requests.ConnectionError):
        _cliente(tmp_path, SesionFalsa(b"", falla=True)).serie(2019, 7, 2019, 7)


def test_la_escritura_en_la_cache_es_atomica_y_no_deja_temporales(tmp_path):
    _cliente(tmp_path, SesionFalsa(FIXTURE.read_bytes())).serie(2019, 7, 2019, 8)

    assert not list(tmp_path.glob("*.tmp"))
