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
| | `/eventos` | Eventos: cambios del ranking y de filings SEC desde una cesta guardada, y sus próximos resultados; destino de las alertas de Hoy (#193) | `market` |
| **Descubrir** | `/descubrir` | Ranking | `market` |
| | `/descubrir/comparar` | Comparar empresas | `market` |
| | `/descubrir/seguidas` | Empresas seguidas: score, posición y cambios desde el alta (#182) | `market` |
| | `/empresas/:symbol` | Ficha de empresa (sin entrada en el menú) | `market` |
| **Cartera** | `/cartera` | Plan de cartera: regla congelada (Top-N equiponderado) o, con `?plan=experimental`, el plan experimental con límites (#191) | `portfolio` |
| | `/cartera/mi-cartera` | Mi cartera (compras reales) | `portfolio` |
| | `/cartera/perfil` | Perfil de inversor y benchmark S&P 500 en EUR con los mismos flujos (#244) | `portfolio` |
| | `/cartera/riesgo` | Riesgo por emisor, política de cartera y órdenes propuestas para una aportación (#248) | `portfolio` |
| | `/cartera/seguimiento` | Seguimiento de cestas guardadas frente a SPY (#193) | `market` |
| | `/cartera/diario` | Diario de inversión | `portfolio` |
| | `/cartera/simuladas` | Carteras simuladas | `portfolio` |
| **Investigación** | `/investigacion/*` | Ensayos, ranking histórico, validaciones ciegas y laboratorios de factores, experimentos y carteras; solo en modo Research (#189) | `research` |
| **Administración** | `/administracion`, `/administracion/calidad` | Datos, claves, modo, trabajos y calidad | `administration` |
| Ayuda (global) | `/ayuda` | Aprender y glosario; enlazada desde la cabecera | `portfolio` |

La cabecera de todas las páginas tiene el buscador de empresas, que lleva a
`/empresas/:symbol`. Lee la lista de empresas la primera vez que recibe el foco,
con la misma consulta que Comparar, no en cada carga de página.

Signal Monitor se reparte en dos sitios (#193): el seguimiento de cestas en
Cartera y los eventos en Hoy. Guardar una cesta es una acción de Cartera objetivo
(«Guardar esta cartera para seguirla»), que guarda exactamente su Top-N elegible.
Ningún nombre de la navegación queda en inglés.

La sección se llama «Cartera» y no «Mi cartera», como proponía la issue, porque
«Mi cartera» ya nombra las compras reales (#181) en la interfaz y en los
mensajes del backend.

La lista de seguimiento de empresas (#182) se llama «Empresas seguidas» y vive en
Descubrir, porque «Seguimiento» ya nombra las cestas guardadas (#193). Se añade y
se quita con «Seguir» en la fila del Ranking, la ficha y Comparar.

## Redirecciones

Las rutas anteriores siguen funcionando: redirigen con `replace` y conservan la
consulta (añadida a la de la ruta nueva, si la tiene) y el ancla (filtros del Ranking, `?symbols=` de Comparar,
`?tab=glosario#termino-…` del glosario).

| Antes | Ahora |
|---|---|
| `/mercado` | `/descubrir` |
| `/mercado/comparar` | `/descubrir/comparar` |
| `/mercado/empresas/:symbol` | `/empresas/:symbol` |
| `/mercado/macro` | `/macro` |
| `/mercado/senales` | `/cartera/seguimiento` |
| `/cartera/aprender` | `/ayuda` |
| `/cartera/decisiones` | `/cartera?plan=experimental` |

Los enlaces que genera el backend (alertas de Hoy) usan ya las rutas nuevas.

## Pruebas

- `frontend/tests/page-title.test.ts`: sección de cada ruta, títulos y destino de
  cada redirección.
- `frontend/tests/e2e/navigation.spec.ts`: menú por tareas, Ayuda en la
  cabecera, buscador global y redirecciones con consulta y ancla.
- `frontend/tests/e2e/mode.spec.ts`: navegación en modo Investor y Research.
