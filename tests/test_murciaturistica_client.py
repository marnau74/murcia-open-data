"""Tests del cliente de murciaturistica.es (sin red)."""

from murcia_data.ingest.murciaturistica_client import BASE_URL, REFERER, MurciaturisticaClient


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
