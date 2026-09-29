# Frontend de GABI

Proyecto separado del backend Python, con su propio `package.json`. El cliente React + TypeScript + Vite,
React Router y shadcn/ui se implementa en la fase [#65](https://github.com/juavepui/GABI/issues/65),
con el [contrato OpenAPI ya implementado en F2](../docs/local-api.md).

Durante esta fase estructural, la interfaz operativa es `../app/` (Streamlit).
Los datos permanecen en `../data/`; el frontend los consultará mediante la API.

La [arquitectura vigente](../docs/architecture.md) fija `src/app`,
`src/features/{market,portfolio,research,administration}` y `src/shared`.
El cliente HTTP vive en `shared/api`; scoring y reglas de evidencia permanecen
en el backend. No hay pantallas React todavía.

Los controles están operativos desde esta fase, con TypeScript fijado en
`package-lock.json` para analizar imports mediante su AST:

```powershell
cd frontend
npm ci --ignore-scripts
npm run lint:architecture
npm run test:architecture
```

La CI ejecuta las reglas y sus pruebas. F3 añadirá React/Vite, contrato generado,
lint general, types, tests de interfaz y build sobre esta estructura.
