import {
  ChartNoAxesCombined,
  BriefcaseBusiness,
  FlaskConical,
  Settings2,
  House,
} from 'lucide-react';
// Sub-sections of each section, shown under it in the sidebar while it is active.
export const subsections: Record<string, { path: string; label: string }[]> = {
  '/mercado': [
    { path: '/mercado', label: 'Ranking' },
    { path: '/mercado/comparar', label: 'Comparar empresas' },
    { path: '/mercado/macro', label: 'Panel macro' },
    { path: '/mercado/senales', label: 'Signal Monitor' },
  ],
  '/cartera': [
    { path: '/cartera', label: 'Cartera objetivo' },
    { path: '/cartera/mi-cartera', label: 'Mi cartera' },
    { path: '/cartera/diario', label: 'Diario de inversión' },
    { path: '/cartera/aprender', label: 'Aprender' },
    { path: '/cartera/simuladas', label: 'Carteras simuladas' },
    { path: '/cartera/decisiones', label: 'Decisiones' },
  ],
  '/investigacion': [
    { path: '/investigacion', label: 'Ensayos registrados' },
    { path: '/investigacion/historico', label: 'Ranking histórico' },
    { path: '/investigacion/validaciones', label: 'Validaciones ciegas' },
    { path: '/investigacion/factores', label: 'Factor Lab' },
    { path: '/investigacion/laboratorio', label: 'Research Lab' },
    { path: '/investigacion/carteras', label: 'Portfolio Lab' },
  ],
  '/administracion': [
    { path: '/administracion', label: 'Datos y modelo' },
    { path: '/administracion/calidad', label: 'Calidad de los datos' },
  ],
};
export const navigation = [
  { path: '/', label: 'Inicio', icon: House },
  { path: '/cartera', label: 'Cartera', icon: BriefcaseBusiness },
  { path: '/mercado', label: 'Mercado', icon: ChartNoAxesCombined },
  { path: '/investigacion', label: 'Investigación', icon: FlaskConical },
  { path: '/administracion', label: 'Administración', icon: Settings2 },
];
/** The tab title, most specific first («APA · Ficha · GABI», «Cartera objetivo · GABI»), so
 *  several open tabs and the browser history can be told apart. */
export function pageTitle(pathname: string, search = ''): string {
  const symbol = /^\/mercado\/empresas\/([^/]+)/.exec(pathname)?.[1];
  const symbols = new URLSearchParams(search).getAll('symbols');
  const sub = Object.values(subsections)
    .flat()
    .find((entry) => entry.path === pathname);
  const item = navigation.find((entry) =>
    entry.path === '/' ? pathname === '/' : pathname.startsWith(entry.path),
  );
  const parts = symbol
    ? [decodeURIComponent(symbol), 'Ficha']
    : pathname === '/mercado/comparar' && symbols.length
      ? ['Comparar ' + symbols.join(', ')]
      : sub
        ? [sub.label]
        : item
          ? [item.label]
          : [];
  return [...parts, 'GABI'].join(' · ');
}
