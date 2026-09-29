"""Indicadores de la web, calculados con SQL sobre la capa gold. Ninguna cifra de la
página se escribe a mano: todo sale de aquí.

Criterio común: las comparaciones entre meses se hacen solo con años completos (los 12
meses publicados en esa fuente y tipo de alojamiento), para que un año con huecos, como
2020, o el año en curso no deformen el perfil estacional.
"""

import duckdb

ZONAS = {"zona-costa": "costa", "zona-ciudad": "ciudad", "zona-interior": "interior"}
TIPOS = ["hotel", "camping", "apartamento", "rural"]

# Demanda de murciaturistica por zona (costa, ciudad, interior) a partir de sus destinos.
_MT_ZONAS = """
    select
        f.fecha_id, d.fecha, d.anio, d.mes,
        case t.padre_id when 'zona-costa' then 'costa' when 'zona-ciudad' then 'ciudad' else 'interior' end as zona,
        f.residencia_id, f.viajeros, f.pernoctaciones
    from gold.fct_demanda_mensual as f
    join gold.dim_fecha as d using (fecha_id)
    join gold.dim_territorio as t using (territorio_id)
    where f.fuente = 'murciaturistica'
"""

# Demanda del INE en la Región por tipo de alojamiento.
_INE_REGION = """
    select f.fecha_id, d.fecha, d.anio, d.mes, f.tipo_alojamiento_id as tipo,
           f.residencia_id, f.viajeros, f.pernoctaciones, f.es_provisional
    from gold.fct_demanda_mensual as f
    join gold.dim_fecha as d using (fecha_id)
    where f.fuente = 'INE' and f.territorio_id = 'region-murcia'
"""


def _filas(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    resultado = con.execute(sql, params or [])
    columnas = [c[0] for c in resultado.description]
    return [dict(zip(columnas, fila, strict=True)) for fila in resultado.fetchall()]


def anios_completos(con: duckdb.DuckDBPyConnection, base: str) -> list[int]:
    """Años con los 12 meses publicados en todos los grupos de `base` (zonas o tipos)."""
    grupo = "zona" if base == _MT_ZONAS else "tipo"
    sql = f"""
        with base as ({base}),
        por_grupo as (
            select anio, {grupo}, count(distinct mes) as meses
            from base where pernoctaciones is not null group by all
        )
        select anio from por_grupo group by anio
        having min(meses) = 12 and count(*) = (select count(distinct {grupo}) from base)
        order by anio
    """
    return [fila["anio"] for fila in _filas(con, sql)]


def perfil_estacional(con: duckdb.DuckDBPyConnection, base: str, anios: list[int]) -> list[dict]:
    """% de las pernoctaciones anuales de cada grupo que cae en cada mes (suma 100)."""
    grupo = "zona" if base == _MT_ZONAS else "tipo"
    sql = f"""
        with base as ({base}),
        por_mes as (
            select {grupo} as grupo, mes, sum(pernoctaciones) as p
            from base where anio in (select unnest(?)) group by all
        )
        select grupo, mes, 100 * p / sum(p) over (partition by grupo) as pct
        from por_mes order by grupo, mes
    """
    return _filas(con, sql, [anios])


def anual(con: duckdb.DuckDBPyConnection, base: str, anios: list[int]) -> list[dict]:
    """Pernoctaciones anuales por grupo e índice con base 100 en 2019."""
    grupo = "zona" if base == _MT_ZONAS else "tipo"
    sql = f"""
        with base as ({base}),
        por_anio as (
            select {grupo} as grupo, anio, sum(pernoctaciones) as pernoctaciones
            from base where anio in (select unnest(?)) group by all
        )
        select grupo, anio, pernoctaciones,
               100 * pernoctaciones / max(pernoctaciones) filter (where anio = 2019) over (partition by grupo) as indice
        from por_anio order by grupo, anio
    """
    return _filas(con, sql, [anios])


def perfil_zonas(con: duckdb.DuckDBPyConnection, anios: list[int]) -> list[dict]:
    """Relación agosto/enero, estancia media y peso del turismo extranjero por zona."""
    sql = f"""
        with base as ({_MT_ZONAS})
        select
            zona,
            sum(pernoctaciones) filter (where mes = 8) / sum(pernoctaciones) filter (where mes = 1)
                as ratio_agosto_enero,
            sum(pernoctaciones) / sum(viajeros) as estancia_media,
            100 * sum(pernoctaciones) filter (where residencia_id = 'extranjero') / sum(pernoctaciones)
                as pct_extranjero
        from base where anio in (select unnest(?))
        group by zona order by zona
    """
    return _filas(con, sql, [anios])


def serie_mensual_tipos(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Pernoctaciones mensuales por tipo en la Región. Los meses sin dato quedan como
    NULL (hueco en el gráfico), nunca como 0."""
    sql = f"""
        with base as ({_INE_REGION}),
        por_mes as (
            select tipo, fecha, sum(pernoctaciones) as pernoctaciones, bool_or(es_provisional) as provisional
            from base group by all
        ),
        calendario as (
            select t.tipo, d.fecha from gold.dim_fecha as d
            cross join (select distinct tipo from base) as t
            where d.fecha <= (select max(fecha) from base)
        )
        select c.tipo, strftime(c.fecha, '%Y-%m') as fecha, p.pernoctaciones,
               coalesce(p.provisional, false) as provisional
        from calendario as c left join por_mes as p using (tipo, fecha)
        order by c.tipo, c.fecha
    """
    return _filas(con, sql)


def empleo(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Personal empleado cada mes por tipo de alojamiento en la Región."""
    sql = """
        select o.tipo_alojamiento_id as tipo, strftime(d.fecha, '%Y-%m') as fecha, d.anio, d.mes,
               o.personal_empleado as personal
        from gold.fct_oferta_mensual as o join gold.dim_fecha as d using (fecha_id)
        where o.territorio_id = 'region-murcia' and o.personal_empleado is not null
        order by tipo, fecha
    """
    return _filas(con, sql)


def precios(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Índice de precios hoteleros (base 2008) de la Región y de España."""
    sql = """
        select p.territorio_id as territorio, strftime(d.fecha, '%Y-%m') as fecha,
               p.indice_precios as indice, p.variacion_interanual as variacion
        from gold.fct_precios_mensual as p join gold.dim_fecha as d using (fecha_id)
        where p.indice_precios is not null
        order by territorio, fecha
    """
    return _filas(con, sql)


def cuadre_fuentes(con: duckdb.DuckDBPyConnection) -> dict:
    """Resumen de la validación cruzada: totales hoteleros del INE frente a la suma de
    destinos de murciaturistica, en los meses que publican las dos."""
    sql = f"""
        with ine as (
            select fecha_id, sum(viajeros) as v, sum(pernoctaciones) as p
            from ({_INE_REGION}) where tipo = 'hotel' group by fecha_id
        ),
        mt as (
            select fecha_id, sum(viajeros) as v, sum(pernoctaciones) as p from ({_MT_ZONAS}) group by fecha_id
        )
        select count(*) as meses,
               max(abs(ine.p - mt.p)) as dif_max_pernoctaciones,
               count(*) filter (where abs(ine.p - mt.p) <= 10) as meses_pernoctaciones_cuadran,
               count(*) filter (where abs(ine.v - mt.v) <= 10) as meses_viajeros_cuadran
        from ine join mt using (fecha_id)
    """
    resumen = _filas(con, sql)[0]
    resumen["excepciones"] = _filas(
        con, "select fecha_id, medida, motivo from ref.excepciones_cuadre order by fecha_id, medida"
    )
    return resumen


def metadatos(con: duckdb.DuckDBPyConnection) -> dict:
    """Periodo cubierto por cada fuente y desde cuándo hay datos provisionales."""
    sql = """
        select
            strftime(min(d.fecha), '%Y-%m') as primer_mes,
            strftime(max(d.fecha) filter (where f.fuente = 'INE'), '%Y-%m') as ultimo_mes_ine,
            strftime(max(d.fecha) filter (where f.fuente = 'murciaturistica'), '%Y-%m') as ultimo_mes_mt,
            strftime(min(d.fecha) filter (where f.es_provisional), '%Y-%m') as provisional_desde
        from gold.fct_demanda_mensual as f join gold.dim_fecha as d using (fecha_id)
    """
    return _filas(con, sql)[0]


def calcular(con: duckdb.DuckDBPyConnection) -> dict:
    """Todos los indicadores de la web."""
    anios_mt = anios_completos(con, _MT_ZONAS)
    anios_ine = anios_completos(con, _INE_REGION)
    return {
        "meta": {**metadatos(con), "anios_completos_mt": anios_mt, "anios_completos_ine": anios_ine},
        "perfil_zonas_mes": perfil_estacional(con, _MT_ZONAS, anios_mt),
        "anual_zonas": anual(con, _MT_ZONAS, anios_mt),
        "perfil_zonas": perfil_zonas(con, anios_mt),
        "perfil_tipos_mes": perfil_estacional(con, _INE_REGION, anios_ine),
        "anual_tipos": anual(con, _INE_REGION, anios_ine),
        "serie_tipos": serie_mensual_tipos(con),
        "empleo": empleo(con),
        "precios": precios(con),
        "cuadre": cuadre_fuentes(con),
    }
