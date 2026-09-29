# Frontend de GABI

Proyecto separado del backend Python, con su propio `package.json`. El cliente React + TypeScript + Vite,
React Router y shadcn/ui se implementa en la fase [#65](https://github.com/juavepui/GABI/issues/65),
cuando exista el contrato OpenAPI de [#64](https://github.com/juavepui/GABI/issues/64).

Durante esta fase estructural, la interfaz operativa es `../app/` (Streamlit).
Los datos permanecen en `../data/`; el frontend los consultará mediante la API.
