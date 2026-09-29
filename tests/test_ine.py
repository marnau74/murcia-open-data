"""Tests del cliente del INE y de la ingesta a la capa raw. No llaman a internet:
usan respuestas reales recortadas en tests/fixtures/ine/."""

import json
from datetime import date
from pathlib import Path

import pytest

from murcia_data.ingest.http import sesion_con_reintentos
from murcia_data.ingest.ine import BASE_URL, IneClient, codigos_del_catalogo, ingerir_series

FIXTURES = Path(__file__).parent / "fixtures" / "ine"


class _Respuesta:
    def __init__(self, datos):
        self._datos = datos

    def raise_for_status(self):
        pass

    def json(self):
        return self._datos


class SesionFalsa:
    """Sustituye a requests.Session: devuelve respuestas fijas y apunta las peticiones."""

    def __init__(self, respuestas: dict[str, object]):
        self.respuestas = respuestas
        self.peticiones: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.peticiones.append((url, params or {}))
        ruta = url.removeprefix(f"{BASE_URL}/")
        return _Respuesta(self.respuestas[ruta])


def _serie_fixture() -> dict:
    return json.loads((FIXTURES / "serie_EOT1772.json").read_text(encoding="utf-8"))


def test_serie_pide_desde_la_fecha_indicada_hasta_el_final():
    sesion = SesionFalsa({"DATOS_SERIE/EOT1772": _serie_fixture()})
    cliente = IneClient(sesion=sesion, pausa=0)

    serie = cliente.serie("EOT1772", desde=date(2015, 1, 1))

    assert serie["COD"] == "EOT1772"
    assert sesion.peticiones == [(f"{BASE_URL}/DATOS_SERIE/EOT1772", {"date": "20150101:"})]


def test_serie_rechaza_una_respuesta_de_otra_serie():
    sesion = SesionFalsa({"DATOS_SERIE/EOT9999": _serie_fixture()})
    cliente = IneClient(sesion=sesion, pausa=0)

    with pytest.raises(ValueError, match="EOT9999"):
        cliente.serie("EOT9999")


def test_ingerir_series_guarda_la_respuesta_tal_cual_por_fecha_de_ingesta(tmp_path):
    sesion = SesionFalsa({"DATOS_SERIE/EOT1772": _serie_fixture()})
    cliente = IneClient(sesion=sesion, pausa=0)

    ficheros = ingerir_series(cliente, ["EOT1772"], tmp_path, fecha_ingesta=date(2026, 9, 29))

    assert ficheros == [tmp_path / "2026-09-29" / "EOT1772.json"]
    assert json.loads(ficheros[0].read_text(encoding="utf-8")) == _serie_fixture()
    assert not list(tmp_path.rglob("*.tmp"))  # la escritura temporal no deja restos


def test_ingerir_series_no_vuelve_a_pedir_lo_ya_ingerido_ese_dia(tmp_path):
    sesion = SesionFalsa({"DATOS_SERIE/EOT1772": _serie_fixture()})
    cliente = IneClient(sesion=sesion, pausa=0)

    ingerir_series(cliente, ["EOT1772"], tmp_path, fecha_ingesta=date(2026, 9, 29))
    ingerir_series(cliente, ["EOT1772"], tmp_path, fecha_ingesta=date(2026, 9, 29))

    assert len(sesion.peticiones) == 1


def test_sesion_reintenta_errores_transitorios():
    adaptador = sesion_con_reintentos().get_adapter(BASE_URL)
    reintentos = adaptador.max_retries

    assert reintentos.total == 5
    assert {429, 500, 502, 503, 504} <= set(reintentos.status_forcelist)
    assert reintentos.backoff_factor > 0


def test_codigos_del_catalogo_lee_el_seed(tmp_path):
    seed = tmp_path / "series.csv"
    seed.write_text("codigo,medida\nEOT1,viajeros\nEOT2,pernoctaciones\n", encoding="utf-8")
    assert codigos_del_catalogo(seed) == ["EOT1", "EOT2"]
