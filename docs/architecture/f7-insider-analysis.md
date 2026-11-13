# F7.4: interpretación de Form 4 y actividad de insiders

`domain/market/insiders.py` interpreta XML de Form 4 y resume filas recibidas.
El día de corte es obligatorio; no lee configuración, SQLite ni SEC y no obtiene
la hora actual. La ficha pasa el reloj del caso de uso `CompanyResearch`.
La fachada `insider.py` conserva su firma pública y captura el día UTC para sus
consumidores antiguos.

Se mantienen las compras P, ventas S, propietarios distintos, valores netos en
dólares y la marca de compras exclusivamente bajo planes 10b5-1. Los nulos se
convierten en cero solo al calcular importes, como antes. Opciones y donaciones
permanecen en las filas recientes, pero no cuentan en el neto. El corte por meses
usa `DateOffset`, incluidos finales de mes; el comportamiento histórico incluye
filas posteriores al día de corte. Cambiar esa regla requiere otra entrega.

Las referencias se capturaron del módulo anterior antes de extraerlo: XML de
compra, venta programada y línea incompleta; seis resúmenes con finales de mes,
duplicidad de compradores, nulos, operaciones no discrecionales y conjuntos
vacíos. Las pruebas comparan todos los campos y filas y comprueban que las
entradas no cambian ni requieren reloj implícito o archivos. La ficha conserva
sus consultas de solo lectura y su contrato HTTP.

Esta entrega no cambia SQL, límites, cachés ni acceso a datos; no se atribuye
una mejora de rendimiento. La entrega posterior de [sincronización](f7-insider-sync.md)
migra documentos, coordinación y almacén del job; la resolución CIK y los lectores
de compatibilidad siguen pendientes junto al núcleo.
No se altera ningún motor congelado. La nueva ruta se incluye solo en metadatos
de futuras versiones del ledger; los registros y hashes históricos permanecen.
