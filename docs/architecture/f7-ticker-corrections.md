# F7.4: correcciones revisadas de etiquetas históricas

El dominio de Investigación corrige etiquetas dentro de intervalos explícitos,
valida nominaciones de CIK y sustituye candidatos comunitarios solo en los
intervalos nominados. Recibe símbolos, día, registros y fuentes; no lee archivos
ni consulta SEC. Los intervalos y fuentes de WellPoint conservan sus valores.

La fachada mantiene rutas a recursos y caché del catálogo revisado. El catálogo
es un recurso publicado estático; esta entrega no añade descargas, invalidación
ni escrituras. Los cuatro consumidores legacy conservan sus firmas hasta migrar
sus flujos. El adaptador nuevo de migración de entidades usa constantes de dominio.

Se mantienen ventanas semiabiertas, error por WLP/ANTM simultáneos, CIK de diez
dígitos, tickers SEC, intervalos solapados, `evidence_window_days`, nominaciones
existentes, fragmentos anteriores/posteriores y exclusión `price_only`.
Los recursos acreditados no cambian; una nominación sigue requiriendo evidencia
SEC y no acredita por sí sola una identidad.

Las futuras preparaciones de revalidación incluyen las rutas efectivas de dominio
SEC, períodos, correcciones y membresía en `extra_sources`. Los manifiestos ya
publicados no se actualizan ni se reesellan: un cache anterior sigue sujeto a la
comprobación de sus fuentes originales y no se mezcla con una ejecución nueva.

Las referencias del original cubren seis correcciones y cinco sustituciones.
Las pruebas comprueban datos sin mutación, validaciones, intervalos adyacentes y
fuentes de salida sin compartir listas mutables. No se cambia acceso a datos ni
se atribuye una mejora de rendimiento. Los comandos históricos siguen pendientes
de su composición explícita y de revisar su procedencia completa al migrar el núcleo.
