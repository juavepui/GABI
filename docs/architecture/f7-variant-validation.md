# F7.4: protocolo de validación de variantes

El dominio de Investigación define `VariantSpec`, las 39 fechas trimestrales
y las métricas por ventana. El caso de uso recibe el runner de backtest como
argumento obligatorio. Valida nombres, parámetros de muestra, fechas y
rebalanceos antes de construir el informe; ningún import ejecuta un backtest.

La fachada `variant_validation.py` conserva el runner por defecto y sus helpers
para R3 congelado y el experimento de rotación. No se cambia ninguno de esos
motores ni se ejecutan sus datos publicados o holdouts para comprobar esta
extracción. El baseline pierde dependencias retiradas; no se añaden excepciones.

El informe completo se compara con la referencia capturada del original sobre
NAV sintético. Se conservan coste inicial, denominador de ventanas internas,
retornos sin solapamiento, CAGR, colas, drawdown, beta y orden de variantes.
También se comprueban entradas sin mutación y protocolos inválidos sin llamadas
al runner. No se cambia acceso a datos ni se atribuye mejora de rendimiento.
