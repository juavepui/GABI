# Reglas de trabajo de GABI

Antes de implementar, leer [la arquitectura vigente](docs/architecture.md) y
[la migración del código existente](docs/architecture/legacy-migration.md).
Estas reglas se aplican a cambios nuevos y a cambios en módulos antiguos.

## Dónde escribir código

- `backend/src/gabi/domain/`: cálculos y reglas financieras puros; sin red,
  ficheros, SQLite, configuración global ni frameworks de interfaz.
- `backend/src/gabi/application/`: casos de uso, DTO internos y puertos
  específicos mediante funciones/dataclasses/Protocol. Depende del dominio;
  recibe repositorios, reloj y configuración por parámetros.
- `backend/src/gabi/infrastructure/`: SQLite, fuentes externas, cachés, jobs y
  ajustes locales. Implementa los puertos de aplicación.
- `backend/src/gabi/infrastructure/legacy/`: único acceso del código nuevo a
  módulos planos existentes. Sin helpers Streamlit. Adaptación explícita,
  pequeña y probada; no copia de fórmulas.
- `backend/src/gabi_api/` y `gabi_cli/`: adaptadores delgados a los mismos casos
  de uso. Solo `bootstrap.py` conecta implementaciones de infraestructura.
- `frontend/src/app/`: composición, navegación y arranque. Importa las features
  por su `index.ts` público.
- `frontend/src/features/{market,portfolio,research,administration}/`: flujos
  de cada capacidad. No importar otra feature ni `app`.
- `frontend/src/shared/{api,ui,lib,assets}/`: cliente HTTP, contratos generados,
  presentación reutilizable y utilidades puras. No importar features/app.

No añadir módulos planos a `gabi` ni páginas Streamlit nuevas. El inventario
`.github/architecture-legacy.json` registra excepciones existentes, no ubicaciones
permitidas para funcionalidad nueva. No ampliar sus excepciones para hacer pasar
CI; al retirar un import o módulo, retirar su excepción. Un módulo antiguo puede
delegar en `domain`/`application` nuevos mientras conserva su interfaz pública.

## Reglas de comportamiento

- Una consulta nueva no descarga datos, modifica SQLite, ejecuta backtests ni
  abre reservas ciegas. Una acción de escritura/descarga/cálculo largo es explícita;
  los jobs persistentes se implementan en F4.
- No modificar configuración global por petición/job para adaptar legacy.
  Settings y conexiones se inyectan por operación; el bootstrap de compatibilidad
  F1 permanece acotado al arranque. Los monkeypatches de tests no son un diseño de producción.
- El backend es autoridad de scoring, filtros, selección, costes, identidad,
  modo Investor/Research y evidencia. React solo presenta y formatea unidades.
- Dependencias sin ciclos en código nuevo. Funciones sencillas antes que
  jerarquías, repositorios genéricos, buses o servicios separados.
  En Python, imports de módulos concretos; no agregar toda una capa en `__init__`.
- No leer todo `data/`, cargar series completas sin límites ni calcular hashes
  completos por render/consulta. Consultas por lotes, ventanas acotadas y cachés
  con invalidación documentada. Medir antes/después en el flujo que se optimiza.
- Conservar unidades, ausencias, fechas, procedencia, hashes y resultados.
  Los 18 motores/configuración congelados no se reformatean, mueven ni reesellan
  para aplicar arquitectura: se usan mediante adaptadores o nuevas versiones.
- Todos los tests usan datos temporales, incluidos pesos, claves y cachés.
  Nunca usar `data/gabi.db`, descargar fuentes o consultar holdouts para validar
  una refactorización.

## Verificación y cambios de arquitectura

Desde la raíz:

```powershell
uv run --project backend python scripts/check_architecture.py
npm --prefix frontend run lint:architecture
npm --prefix frontend run test:architecture
uv run --project backend ruff check .
uv run --project backend python -m gabi_cli research frozen --check-frozen
```

Ejecutar los tests pertinentes y los controles de tipos/contrato del código
modificado. La CI ejecuta ambos controles de arquitectura y la suite Python.
Las guardas son estáticas: equivalencia financiera, ausencia de efectos en GET,
rendimiento e invalidación requieren tests y revisión del caso de uso.

Si hace falta cambiar un límite, justificarlo en un ADR de `docs/adr/`, actualizar
la arquitectura y sus pruebas en el mismo cambio. No añadir excepciones generales
ni desactivar una guarda. Refactorización estructural y cambio de estrategia se
entregan con validaciones separadas. La #60 sigue pendiente de evidencia.
