# F7.4: factores académicos y carga explícita del worker

La interpretación mensual, composición y OLS/HAC viven en dominio. Conservan
porcentajes convertidos a fracciones, ventanas mensuales de inicio incluido/fin
excluido, RF, raíz y corrección HAC/Bartlett, retardos automáticos, grados de
libertad, diagnósticos clásicos y anualización. Las columnas de referencia son
inmutables en dominio; la fachada conserva su lista pública mutable y la pasa
explícitamente cuando se utiliza desde motores legacy.

El caso de uso comparte interpretación y combinación entre la fachada y los
puertos actuales. La lectura de caché no recibe una fuente ni puede descargar.
El job de contraste permite refrescar explícitamente cuando falta la caché;
el bootstrap del worker compone fuente HTTP, caché y función de carga, con el
directorio de settings. No se cambia configuración global por operación.

El proveedor conserva URLs, cabecera, timeout de 30 s, primer CSV del ZIP y
decodificación UTF-8 con reemplazo. Limita respuesta comprimida a 2 MB y CSV
a 8 MB; consume el HTTP por bloques de 64 KB y cierra la respuesta. La caché
limita el archivo a 2 MB y 5.000 meses: rechaza excesos,
no recorta datos. Escribe por reemplazo atómico con los mismos bytes CSV del
original y devuelve las métricas frescas sin un roundtrip adicional que pueda
cambiar su precisión. El lector obtiene datos y SHA-256 de los mismos bytes.

La invalidación sigue siendo explícita: la caché mensual no tiene TTL; se
reutiliza hasta pedir refresco o borrarla mediante una acción de mantenimiento.
No se convierte un GET en descarga cuando falta el archivo. El job permite
la descarga porque es una acción persistente autorizada de cálculo.

`academic_factors.py` permanece como fachada: los motores congelados usan su
interfaz y `__file__` para hashes. No se cambian sus bytes ni manifests publicados.
La fachada mantiene sus adaptadores I/O de compatibilidad, sin fórmulas duplicadas;
el worker actual usa puertos inyectados. Los nuevos artefactos completos del
contraste registran `calculation_sources` para las rutas efectivas de dominio y
aplicación. Los manifests sellados se verifican/reproducen en sus commits
originales; no se reesella ninguna publicación para hacerla coincidir con código
actual. F7 permanece pendiente de las demás fuentes, almacenamiento y núcleo.

Las pruebas ejecutan la fuente original capturada en un namespace privado, con
datos sintéticos y archivos temporales. Comparan todos los resultados de OLS/HAC,
regresiones de distintas periodicidades, caché, unidades y bytes CSV. Comprueban
límites, consulta sin escritura/red, refresco explícito y composición del worker.

Medición de lectura/caché reproducible:
`.venv/Scripts/python.exe scripts/measure_f7_academic_factors.py`.
Se mide el mismo archivo sintético y hash, sin llamadas de red ni reservas.

En Windows/Python 3.13, 768 meses/7 columnas y archivo de 111.784 bytes:
30 lecturas medidas, medianas original 0,01909 s y migrada 0,01960 s, picos de
asignaciones Python 0,382 y 0,337 MiB. La primera lectura medida tarda 0,02064
y 0,01994 s respectivamente, después de preparar la referencia; no es una
medida de caché fría del SO. Todos los valores y SHA-256 coinciden; cero
descargas. La entrega no acredita una mejora general de velocidad ni mide RSS.
