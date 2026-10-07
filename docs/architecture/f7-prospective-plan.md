# F7.4: plan prospectivo y verificación de preregistros

Se retira `prospective_plan.py`: sus dos adaptadores usan dominio y proveedor
estadístico directamente. El comando actual es `gabi_cli research prospective-plan`
con las opciones de escritura explícita y plan fijo descritas en su ayuda.

El dominio conserva gasto de alfa, correlaciones entre revisiones, raíces,
potencia, textos y hash JSON. La CDF multivariante es un puerto obligatorio;
la integración numérica de SciPy queda en infraestructura, conservando su método
y comportamiento por defecto. Se puede inyectar RNG para nuevas operaciones;
esta migración no cambia semillas, umbrales ni planes publicados.

El cálculo secuencial original ya dependía de integración numérica estocástica;
no se presenta como una operación de precisión exacta determinista. Las pruebas
de extracción usan la misma CDF sintética en ambas versiones para comparar todas
las operaciones, además de la prueba existente con SciPy real. Los hashes de
registros recibidos y la salida JSON se comparan exactamente contra el original.

La publicación recibe escritor y directorio; el preview no crea archivos ni
consulta datos ciegos. Ambos artefactos se escriben solo en directorios temporales
durante los tests. La API verifica los preregistros con el mismo hash y formatos;
no se regeneran ni se reesellan documentos de #42/#43.
