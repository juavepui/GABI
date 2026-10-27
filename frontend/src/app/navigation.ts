import {
  BriefcaseBusiness,
  FlaskConical,
  Search,
  Settings2,
  Sun,
  type LucideIcon,
} from 'lucide-react';

export type Page = { path: string; label: string };
export type Section = {
  path: string;
  label: string;
  icon: LucideIcon;
  /** Its pages, listed under it in the sidebar while it is active. */
  pages: Page[];
  /** Other routes that belong to it without a menu entry (a company page). */
  prefixes?: string[];
};

/** Sections by investor task (docs/frontend-routes.md); Investigación only in Research mode. */
export const sections: Section[] = [
  {
    path: '/',
    label: 'Hoy',
    icon: Sun,
    pages: [
      { path: '/', label: 'Resumen' },
      { path: '/macro', label: 'Panel macro' },
      { path: '/eventos', label: 'Eventos' },
    ],
  },
  {
    path: '/descubrir',
    label: 'Descubrir',
    icon: Search,
    pages: [
      { path: '/descubrir', label: 'Ranking' },
      { path: '/descubrir/comparar', label: 'Comparar empresas' },
      { path: '/descubrir/seguidas', label: 'Empresas seguidas' },
    ],
    prefixes: ['/empresas/'],
  },
  {
    path: '/cartera',
    label: 'Cartera',
    icon: BriefcaseBusiness,
    pages: [
      { path: '/cartera', label: 'Cartera objetivo' },
      { path: '/cartera/mi-cartera', label: 'Mi cartera' },
      { path: '/cartera/seguimiento', label: 'Seguimiento' },
      { path: '/cartera/diario', label: 'Diario de inversión' },
      { path: '/cartera/simuladas', label: 'Carteras simuladas' },
    ],
  },
  {
    path: '/investigacion',
    label: 'Investigación',
    icon: FlaskConical,
    pages: [
      { path: '/investigacion', label: 'Ensayos registrados' },
      { path: '/investigacion/historico', label: 'Ranking histórico' },
      { path: '/investigacion/validaciones', label: 'Validaciones ciegas' },
      { path: '/investigacion/factores', label: 'Laboratorio de factores' },
      { path: '/investigacion/laboratorio', label: 'Laboratorio de experimentos' },
      { path: '/investigacion/carteras', label: 'Laboratorio de carteras' },
    ],
  },
  {
    path: '/administracion',
    label: 'Administración',
    icon: Settings2,
    pages: [
      { path: '/administracion', label: 'Datos y modelo' },
      { path: '/administracion/calidad', label: 'Calidad de los datos' },
    ],
  },
];

/** Help is global: reached from the header on every page, not a section. */
export const HELP: Page = { path: '/ayuda', label: 'Ayuda' };

/** Routes before #188 and where they live now; search and hash are kept on the way. */
export const REDIRECTS: { from: string; to: (params: Record<string, string>) => string }[] = [
  { from: '/mercado', to: () => '/descubrir' },
  { from: '/mercado/comparar', to: () => '/descubrir/comparar' },
  { from: '/mercado/empresas/:symbol', to: ({ symbol }) => '/empresas/' + symbol },
  { from: '/mercado/macro', to: () => '/macro' },
  { from: '/mercado/senales', to: () => '/cartera/seguimiento' },
  { from: '/cartera/aprender', to: () => '/ayuda' },
  { from: '/cartera/decisiones', to: () => '/cartera?plan=experimental' },
];

/** The section a route belongs to: one of its pages, a sub-route of it, or one of its prefixes. */
export function sectionOf(pathname: string): Section | undefined {
  return (
    sections.find((section) => section.pages.some((page) => page.path === pathname)) ??
    sections.find(
      (section) =>
        (section.path !== '/' && pathname.startsWith(section.path + '/')) ||
        section.prefixes?.some((prefix) => pathname.startsWith(prefix)),
    )
  );
}

export function companySymbol(pathname: string): string | undefined {
  const symbol = /^\/empresas\/([^/]+)/.exec(pathname)?.[1];
  return symbol && decodeURIComponent(symbol);
}

/** The tab title, most specific first («APA · Ficha · GABI», «Cartera objetivo · GABI»), so
 *  several open tabs and the browser history can be told apart. */
export function pageTitle(pathname: string, search = ''): string {
  const symbol = companySymbol(pathname);
  const symbols = new URLSearchParams(search).getAll('symbols');
  const section = sectionOf(pathname);
  const page = section?.pages.find((entry) => entry.path === pathname);
  const parts = symbol
    ? [symbol, 'Ficha']
    : pathname === '/descubrir/comparar' && symbols.length
      ? ['Comparar ' + symbols.join(', ')]
      : pathname === '/cartera' && new URLSearchParams(search).get('plan') === 'experimental'
        ? ['Plan experimental']
        : pathname === HELP.path
          ? [HELP.label]
          : page
            ? [page.label]
            : section
              ? [section.label]
              : [];
  return [...parts, 'GABI'].join(' · ');
}
