# Mapa de rutas del frontend

La navegación se organiza por lo que hace un inversor, no por cómo se construyó
GABI (#188). La fuente única es `frontend/src/app/navigation.ts`: secciones,
apartados, pertenencia de cada ruta, título de pestaña y redirecciones. Las
rutas se declaran en `frontend/src/app/app.tsx`; las features no conocen la
navegación ni se importan entre sí.

## Secciones

| Sección | Ruta | Apartado | Feature |
|---|---|---|---|
| **Hoy** | `/` | Resumen: alertas, cartera objetivo de hoy, estado de los datos | `app` |
| | `/macro` | Panel macro | `market` |
| **Descubrir** | `/descubrir` | Ranking | `market` |
| | `/descubrir/comparar` | Comparar empresas | `market` |
| | `/empresas/:symbol` | Ficha de empresa (sin entrada en el menú) | `market` |
| **Cartera** | `/cartera` | Cartera objetivo | `portfolio` |
| | `/cartera/mi-cartera` | Mi cartera (compras reales) | `portfolio` |
| | `/cartera/seguimiento` | Signal Monitor | `market` |
| | `/cartera/diario` | Diario de inversión | `portfolio` |
| | `/cartera/simuladas` | Carteras simuladas | `portfolio` |
| | `/cartera/decisiones` | Decisiones | `portfolio` |
| **Investigación** | `/investigacion/*` | Laboratorios; solo en modo Research (#189) | `research` |
| **Administración** | `/administracion`, `/administracion/calidad` | Datos, claves, modo, trabajos y calidad | `administration` |
| Ayuda (global) | `/ayuda` | Aprender y glosario; enlazada desde la cabecera | `portfolio` |

La cabecera de todas las páginas tiene el buscador de empresas, que lleva a
`/empresas/:symbol`. Lee la lista de empresas la primera vez que recibe el foco,
con la misma consulta que Comparar, no en cada carga de página.

La sección se llama «Cartera» y no «Mi cartera», como proponía la issue, porque
«Mi cartera» ya nombra las compras reales (#181) en la interfaz y en los
mensajes del backend.

## Redirecciones

Las rutas anteriores siguen funcionando: redirigen con `replace` y conservan la
consulta y el ancla (filtros del Ranking, `?symbols=` de Comparar,
`?tab=glosario#termino-…` del glosario).

| Antes | Ahora |
|---|---|
| `/mercado` | `/descubrir` |
| `/mercado/comparar` | `/descubrir/comparar` |
| `/mercado/empresas/:symbol` | `/empresas/:symbol` |
| `/mercado/macro` | `/macro` |
| `/mercado/senales` | `/cartera/seguimiento` |
| `/cartera/aprender` | `/ayuda` |

Los enlaces que genera el backend (alertas de Hoy) usan ya las rutas nuevas.

## Pruebas

- `frontend/tests/page-title.test.ts`: sección de cada ruta, títulos y destino de
  cada redirección.
- `frontend/tests/e2e/navigation.spec.ts`: menú por tareas, Ayuda en la
  cabecera, buscador global y redirecciones con consulta y ancla.
- `frontend/tests/e2e/mode.spec.ts`: navegación en modo Investor y Research.
