# 0004 · Validación cruzada entre fuentes con excepciones documentadas

- **Estado:** aceptada
- **Fecha:** 2026-09-29

## Contexto

murciaturistica.es y el INE publican datos de la misma encuesta (la Encuesta de
Ocupación Hotelera): la suma de los destinos turísticos de murciaturistica debería
coincidir con el total hotelero regional del INE. Comprobarlo detecta errores de
ingesta o de transformación que ningún test de una sola fuente vería.

Con los datos reales (enero de 2015 a diciembre de 2024, 115 meses comunes):

- Los **totales** coinciden salvo por redondeo: como máximo 5 pernoctaciones de
  diferencia en un mes de ~300.000.
- Excepción: de **agosto a diciembre de 2016** el INE da entre 97 y 287 **viajeros**
  más (0,11-0,24 %), aunque las pernoctaciones cuadran. La causa no está confirmada;
  lo más probable es una revisión del INE que murciaturistica no trasladó.
- El **reparto por residencia** (España / extranjero) difiere algo más, aunque las
  diferencias se compensan entre sí: en el año, el peso del turismo extranjero varía
  como mucho 0,11 puntos entre fuentes.

## Decisión

- Test **estricto** (`assert_ine_cuadra_con_murciaturistica`) sobre los totales, con una
  tolerancia de redondeo: error si la diferencia supera 10 unidades **y** el 0,05 %.
- Las diferencias estudiadas se registran en el seed `excepciones_cuadre`, una fila por
  mes y medida **con su motivo**. El test las excluye solo para ese mes y esa medida.
- Test de **aviso** (`severity: warn`) sobre el reparto por residencia: avisa si un mes
  se desvía más de un 5 %, sin bloquear la publicación.

## Alternativas descartadas

- **Subir la tolerancia** hasta que pase: ocultaría errores nuevos del mismo tamaño.
- **Quitar el test:** se perdería la única comprobación entre fuentes independientes.
- **Hacer estricto el reparto por residencia:** bloquearía la publicación por una
  diferencia conocida, pequeña y que no afecta a los totales.

## Consecuencias

- Cualquier diferencia nueva entre fuentes para la publicación hasta que se estudie y,
  si procede, se documente en el seed. La lista de excepciones es visible y revisable.
- El README puede afirmar con datos que las dos fuentes cuadran.
