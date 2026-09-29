"""Catálogo de series del INE que usa el proyecto.

Cada serie del INE tiene un código estable y unos metadatos estructurados (territorio,
concepto, residencia...). Aquí se decide qué tablas interesan y cómo se traduce cada
serie a las dimensiones del proyecto. El resultado se guarda como seed de dbt
(`dbt/seeds/series_ine.csv`), revisado y versionado: la ingesta diaria no depende de
interpretar nombres, solo de esa lista de códigos.

Si el INE publica un valor de metadatos que no está en los diccionarios de abajo, la
generación falla: es preferible revisar a mano que clasificar mal una serie.
"""

from __future__ import annotations

from dataclasses import dataclass

COLUMNAS = [
    "codigo",
    "operacion",
    "tabla_id",
    "hecho",
    "tipo_alojamiento",
    "territorio",
    "nivel_territorio",
    "medida",
    "residencia",
    "unidad",
    "nombre_ine",
]


@dataclass(frozen=True)
class Tabla:
    id: int
    operacion: str  # EOH, EOAP, EOAC, EOTR, IPH
    tipo_alojamiento: str  # hotel, apartamento, camping, rural
    hecho: str  # demanda, oferta, precios


TABLAS = [
    # Hoteles (EOH)
    Tabla(2074, "EOH", "hotel", "demanda"),  # comunidades y provincias
    Tabla(2039, "EOH", "hotel", "demanda"),  # zonas turísticas
    Tabla(2078, "EOH", "hotel", "demanda"),  # puntos turísticos
    Tabla(2066, "EOH", "hotel", "oferta"),
    Tabla(2013, "EOH", "hotel", "oferta"),
    Tabla(2076, "EOH", "hotel", "oferta"),
    # Apartamentos turísticos (EOAP)
    Tabla(2063, "EOAP", "apartamento", "demanda"),
    Tabla(2019, "EOAP", "apartamento", "demanda"),
    Tabla(2082, "EOAP", "apartamento", "demanda"),
    Tabla(2072, "EOAP", "apartamento", "oferta"),
    Tabla(2022, "EOAP", "apartamento", "oferta"),
    Tabla(2083, "EOAP", "apartamento", "oferta"),
    # Campings (EOAC)
    Tabla(2062, "EOAC", "camping", "demanda"),
    Tabla(2047, "EOAC", "camping", "demanda"),
    Tabla(2084, "EOAC", "camping", "demanda"),
    Tabla(2064, "EOAC", "camping", "oferta"),
    Tabla(2049, "EOAC", "camping", "oferta"),
    Tabla(2085, "EOAC", "camping", "oferta"),
    # Turismo rural (EOTR): solo publica provincia para Murcia
    Tabla(2073, "EOTR", "rural", "demanda"),
    Tabla(2070, "EOTR", "rural", "oferta"),
    # Índice de precios hoteleros (IPH): comunidad autónoma y total nacional
    Tabla(12156, "IPH", "hotel", "precios"),
]

# (variable del INE, valor) -> (territorio, nivel)
TERRITORIOS = {
    ("Comunidades y Ciudades Autónomas", "Murcia, Región de"): ("region-murcia", "region"),
    ("Provincias", "Murcia"): ("region-murcia", "region"),  # provincia única: misma geografía
    ("ZONAS TURÍSTICAS", "Murcia (Región De): Costa Cálida"): ("costa-calida", "zona"),
    ("PUNTOS TURISTÍCOS", "Cartagena"): ("cartagena", "punto"),
    ("PUNTOS TURISTÍCOS", "Murcia"): ("murcia-municipio", "punto"),
    ("Totales Territoriales", "Total Nacional"): ("espana", "pais"),
}
# Solo se admite el total nacional en precios (para comparar la Región con España).
TERRITORIOS_SOLO_PRECIOS = {"espana"}

MEDIDAS = {
    "Viajero": "viajeros",
    "Pernoctaciones": "pernoctaciones",
    "Número de establecimientos abiertos estimados": "establecimientos",
    "Número de habitaciones estimadas": "habitaciones",
    "Número de plazas estimadas": "plazas",
    "Número de apartamentos estimados": "apartamentos",
    "Número de parcelas": "parcelas",
    "Parcelas ocupadas": "parcelas_ocupadas",
    "Personal empleado": "personal_empleado",
    "Grado de ocupación por plazas": "ocupacion_plazas",
    "Grado de ocupación por plazas en fin de semana": "ocupacion_plazas_fin_semana",
    "Grado de ocupación por habitaciones": "ocupacion_habitaciones",
    "Grado de ocupación por apartamentos": "ocupacion_apartamentos",
    "Grado de ocupación por apartamentos en fin de semana": "ocupacion_apartamentos_fin_semana",
    "Grado de ocupación por parcelas": "ocupacion_parcelas",
    "Grado de ocupación de parcelas en fin de semana": "ocupacion_parcelas_fin_semana",
}
# En el IPH el concepto es siempre "Índice de precios"; lo que cambia es el tipo de dato.
MEDIDAS_PRECIOS = {
    "Índice": "indice_precios",
    "Tasa de variación interanual": "variacion_interanual_precios",
}

RESIDENCIAS = {
    "Residentes en España": "espana",
    "Residentes en el Extranjero": "extranjero",
    "Residentes en el extranjero": "extranjero",
}
VARIABLE_RESIDENCIA = "RESIDENCIA/ORIGEN"
VARIABLE_TERRITORIO = {variable for variable, _ in TERRITORIOS}


class MetadatoDesconocido(ValueError):
    """El INE publica un valor que el catálogo no sabe clasificar."""


def _metadatos(serie: dict) -> dict[str, str]:
    return {md["T3_Variable"]: md["Nombre"] for md in serie.get("MetaData", [])}


def clasificar_serie(serie: dict, tabla: Tabla) -> dict | None:
    """Traduce una serie del INE a una fila del catálogo, o None si no interesa
    (otro territorio, totales derivables, categorías concretas de establecimiento)."""
    md = _metadatos(serie)

    territorios = [TERRITORIOS[(v, md[v])] for v in VARIABLE_TERRITORIO if (v, md.get(v)) in TERRITORIOS]
    if not territorios:
        return None
    territorio, nivel = territorios[0]
    if territorio in TERRITORIOS_SOLO_PRECIOS and tabla.hecho != "precios":
        return None

    if md.get("TIPO DE CATEGORIA", "Total categorías") != "Total categorías":
        return None  # nos quedamos con el total, no con hoteles de 5 estrellas, etc.

    residencia = md.get(VARIABLE_RESIDENCIA)
    if residencia == "Total":
        return None  # se recalcula sumando España + extranjero
    if residencia is not None and residencia not in RESIDENCIAS:
        raise MetadatoDesconocido(f"Residencia desconocida en {serie['COD']}: {residencia!r}")

    if tabla.hecho == "precios":
        tipo_dato = md.get("Tipo de dato")
        if tipo_dato not in MEDIDAS_PRECIOS:
            raise MetadatoDesconocido(f"Tipo de dato desconocido en {serie['COD']}: {tipo_dato!r}")
        medida = MEDIDAS_PRECIOS[tipo_dato]
    else:
        if md.get("Tipo de dato", "Dato") != "Dato":
            return None
        concepto = md.get("Concepto turístico")
        if concepto not in MEDIDAS:
            raise MetadatoDesconocido(f"Concepto desconocido en {serie['COD']}: {concepto!r}")
        medida = MEDIDAS[concepto]

    return {
        "codigo": serie["COD"],
        "operacion": tabla.operacion,
        "tabla_id": tabla.id,
        "hecho": tabla.hecho,
        "tipo_alojamiento": tabla.tipo_alojamiento,
        "territorio": territorio,
        "nivel_territorio": nivel,
        "medida": medida,
        "residencia": RESIDENCIAS.get(residencia, ""),
        "unidad": (serie.get("T3_Unidad") or "").strip(),
        "nombre_ine": serie["Nombre"].strip(),
    }


def construir_catalogo(metadatos_por_tabla: dict[int, list[dict]]) -> list[dict]:
    """Filas del catálogo para todas las tablas, sin duplicados.

    Una misma combinación (hecho, alojamiento, territorio, medida, residencia) puede
    aparecer en varias tablas o dos veces en la misma (p. ej. la tabla 2074 repite
    Murcia como comunidad y como provincia). Se conserva la primera aparición.
    """
    filas, vistas = [], set()
    for tabla in TABLAS:
        for serie in metadatos_por_tabla[tabla.id]:
            fila = clasificar_serie(serie, tabla)
            if fila is None:
                continue
            clave = (fila["hecho"], fila["tipo_alojamiento"], fila["territorio"], fila["medida"], fila["residencia"])
            if clave in vistas:
                continue
            vistas.add(clave)
            filas.append(fila)
    return sorted(filas, key=lambda f: (f["hecho"], f["tipo_alojamiento"], f["nivel_territorio"], f["codigo"]))
