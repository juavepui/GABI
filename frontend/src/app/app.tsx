import { useEffect, useRef } from 'react';
import { BrowserRouter, NavLink, Route, Routes, useLocation, Link } from 'react-router-dom';
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  ChartNoAxesCombined,
  BriefcaseBusiness,
  FlaskConical,
  Settings2,
  HardDrive,
  Leaf,
  House,
} from 'lucide-react';
import {
  MarketPage,
  CompanyPage,
  ComparisonPage,
  MacroPage,
  SignalPage,
} from '@/features/market/index';
import {
  DecisionsPage,
  JournalPage,
  LearnPage,
  PortfolioPage,
  SimulationsPage,
} from '@/features/portfolio/index';
import {
  BlindValidationsPage,
  FactorPage,
  HistoricalPage,
  PortfolioLabPage,
  ResearchLabPage,
  ResearchPage,
} from '@/features/research/index';
import { AdministrationPage, DataHealthPage } from '@/features/administration/index';
import { ApiError } from '@/shared/api/client';
import { HomePage } from './home-page';
import { JobsIndicator } from './jobs-indicator';
import { rememberLaunch } from './job-launches';

// Any mutation that returns a job (it was queued or cancelled) refreshes the job lists at once,
// so the header indicator shows it without waiting for its next poll.
const isJob = (value: unknown) =>
  typeof value === 'object' &&
  value !== null &&
  'kind' in value &&
  'status' in value &&
  'phase' in value;
const client: QueryClient = new QueryClient({
  mutationCache: new MutationCache({
    onSuccess: (data) => {
      if (!isJob(data)) return;
      rememberLaunch(data);
      void client.invalidateQueries({ queryKey: ['jobs'] });
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 300_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status === 409),
    },
  },
});
// Sub-sections of each section, shown under it in the sidebar while it is active.
const subsections: Record<string, { path: string; label: string }[]> = {
  '/mercado': [
    { path: '/mercado', label: 'Ranking' },
    { path: '/mercado/comparar', label: 'Comparar empresas' },
    { path: '/mercado/macro', label: 'Panel macro' },
    { path: '/mercado/senales', label: 'Signal Monitor' },
  ],
  '/cartera': [
    { path: '/cartera', label: 'Cartera objetivo' },
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
const subLink = ({ isActive }: { isActive: boolean }) =>
  'block shrink-0 rounded-md px-3 py-1.5 text-[13px] transition-colors ' +
  (isActive
    ? 'bg-white/15 font-semibold text-white'
    : 'text-[#c5d8cc] hover:bg-white/10 hover:text-white');
const navigation = [
  { path: '/', label: 'Inicio', icon: House },
  { path: '/cartera', label: 'Cartera', icon: BriefcaseBusiness },
  { path: '/mercado', label: 'Mercado', icon: ChartNoAxesCombined },
  { path: '/investigacion', label: 'Investigación', icon: FlaskConical },
  { path: '/administracion', label: 'Administración', icon: Settings2 },
];
/** «GABI / Sección / Apartado»: where the page sits, with links back up. */
function Breadcrumb({ pathname, section }: { pathname: string; section?: string }) {
  const item = navigation.find((entry) =>
    entry.path === '/' ? pathname === '/' : pathname.startsWith(entry.path),
  );
  const sub = section ? subsections[section].find((entry) => entry.path === pathname) : undefined;
  const symbol = /^\/mercado\/empresas\/([^/]+)/.exec(pathname)?.[1];
  const trail: { label: string; to?: string }[] = [{ label: 'GABI', to: '/' }];
  if (item) trail.push({ label: item.label, to: item.path });
  if (sub) trail.push({ label: sub.label });
  if (symbol)
    trail.push({ label: 'Ranking', to: '/mercado' }, { label: decodeURIComponent(symbol) });
  if (!item) trail.push({ label: 'Navegación' });
  return (
    <nav aria-label="Ruta" className="min-w-0 truncate text-xs text-muted-foreground">
      <ol className="flex items-center">
        {trail.map((step, index) => {
          const last = index === trail.length - 1;
          return (
            <li key={step.label + index} className="flex min-w-0 items-center">
              {index > 0 && (
                <span className="mx-2 text-border" aria-hidden="true">
                  /
                </span>
              )}
              {step.to && !last ? (
                <Link to={step.to} className="hover:text-foreground hover:underline">
                  {step.label}
                </Link>
              ) : (
                <span
                  className={last ? 'truncate text-foreground' : ''}
                  aria-current={last ? 'page' : undefined}
                >
                  {step.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
function Shell() {
  const location = useLocation();
  const section = Object.keys(subsections).find((path) => location.pathname.startsWith(path));
  const main = useRef<HTMLElement>(null);
  const mainNav = useRef<HTMLElement>(null);
  const subNav = useRef<HTMLElement>(null);
  useEffect(() => {
    // On narrow screens the menus scroll sideways: bring the active section and sub-page into view.
    for (const nav of [mainNav.current, subNav.current]) {
      const active = nav?.querySelector<HTMLElement>('[aria-current="page"]');
      if (!nav || !active || nav.scrollWidth <= nav.clientWidth) continue;
      nav.scrollLeft = active.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2;
    }
  }, [location.pathname]);
  const previous = useRef(location.pathname);
  useEffect(() => {
    if (previous.current !== location.pathname) {
      previous.current = location.pathname;
      // A link with an anchor (e.g. /administracion#modo) scrolls to it itself; do not undo that.
      if (location.hash) return;
      main.current?.focus();
      window.scrollTo(0, 0);
    }
  }, [location.pathname, location.hash]);
  return (
    <div className="min-h-screen lg:pl-60">
      <a
        href="#contenido"
        className="sr-only z-50 rounded-md bg-primary p-3 text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Saltar al contenido
      </a>
      <aside className="bg-primary text-primary-foreground lg:fixed lg:inset-y-0 lg:left-0 lg:flex lg:w-60 lg:flex-col">
        <Link
          to="/"
          aria-label="GABI, inicio"
          className="flex items-center gap-3 px-5 py-3 lg:px-7 lg:py-8"
        >
          <span className="flex size-8 items-center justify-center rounded-xl bg-white/10 lg:size-10">
            <Leaf size={20} aria-hidden="true" />
          </span>
          <span>
            <span className="block text-lg font-semibold tracking-[0.14em] lg:text-xl">GABI</span>
            <span className="hidden text-[11px] tracking-wide text-[#c5d8cc] lg:block">
              Análisis con evidencia
            </span>
          </span>
        </Link>
        <p className="hidden px-7 pb-3 text-[10px] uppercase tracking-[0.18em] text-[#b7cebf] lg:block">
          Espacio de trabajo
        </p>
        <nav
          aria-label="Navegación principal"
          ref={mainNav}
          className="relative flex gap-1 overflow-x-auto px-3 pb-2 lg:flex-col lg:px-4 lg:pb-3"
        >
          {navigation.map((item) => (
            <div key={item.path} className="contents lg:block">
              <NavLink
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  'flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors lg:py-3 ' +
                  (isActive
                    ? 'bg-[#dceaca] font-semibold text-[#183e32]' +
                      // With its sub-sections listed below, the sub-section carries the highlight.
                      (subsections[item.path] ? ' lg:bg-transparent lg:text-white' : '')
                    : 'text-[#d5e3da] hover:bg-white/10')
                }
              >
                <item.icon size={18} aria-hidden="true" />
                {item.label}
              </NavLink>
              {item.path === section && subsections[item.path] && (
                <ul
                  aria-label={'Apartados de ' + item.label}
                  className="ml-6 mt-1 mb-2 hidden space-y-0.5 border-l border-white/15 pl-2 lg:block"
                >
                  {subsections[item.path].map((sub) => (
                    <li key={sub.path}>
                      <NavLink to={sub.path} end className={subLink}>
                        {sub.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </nav>
        {section && subsections[section] && (
          <nav
            ref={subNav}
            aria-label="Apartados de la sección"
            className="relative flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden"
          >
            {subsections[section].map((sub) => (
              <NavLink key={sub.path} to={sub.path} end className={subLink}>
                {sub.label}
              </NavLink>
            ))}
          </nav>
        )}
        <div className="mt-auto hidden px-5 pb-6 lg:block">
          <div className="rounded-xl border border-white/15 bg-white/5 p-4">
            <p className="flex items-center gap-2 text-xs font-medium">
              <HardDrive size={14} aria-hidden="true" />
              Tu instalación local
            </p>
            <p className="mt-2 text-[11px] leading-relaxed text-[#c5d8cc]">
              Datos y cálculos permanecen en este equipo.
            </p>
          </div>
        </div>
      </aside>
      <header className="flex h-12 items-center justify-between gap-3 border-b bg-card px-5 lg:h-16 lg:px-9">
        <Breadcrumb pathname={location.pathname} section={section} />
        <div className="flex items-center gap-2">
          <JobsIndicator />
          <span className="hidden items-center gap-2 rounded-full border bg-background px-3 py-1 text-[11px] font-medium sm:inline-flex">
            <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
            Entorno local
          </span>
        </div>
      </header>
      <main
        id="contenido"
        ref={main}
        tabIndex={-1}
        className="mx-auto max-w-[1480px] px-4 py-7 focus:outline-none sm:px-6 lg:px-9 lg:py-9"
      >
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/mercado" element={<MarketPage />} />
          <Route path="/mercado/empresas/:symbol" element={<CompanyPage />} />
          <Route path="/mercado/comparar" element={<ComparisonPage />} />
          <Route path="/mercado/macro" element={<MacroPage />} />
          <Route path="/mercado/senales" element={<SignalPage />} />
          <Route path="/cartera" element={<PortfolioPage />} />
          <Route path="/cartera/diario" element={<JournalPage />} />
          <Route path="/cartera/aprender" element={<LearnPage />} />
          <Route path="/cartera/simuladas" element={<SimulationsPage />} />
          <Route path="/cartera/decisiones" element={<DecisionsPage />} />
          <Route path="/investigacion" element={<ResearchPage />} />
          <Route path="/investigacion/historico" element={<HistoricalPage />} />
          <Route path="/investigacion/validaciones" element={<BlindValidationsPage />} />
          <Route path="/investigacion/factores" element={<FactorPage />} />
          <Route path="/investigacion/laboratorio" element={<ResearchLabPage />} />
          <Route path="/investigacion/carteras" element={<PortfolioLabPage />} />
          <Route path="/administracion" element={<AdministrationPage />} />
          <Route path="/administracion/calidad" element={<DataHealthPage />} />
          <Route
            path="*"
            element={
              <div>
                <h1 className="text-2xl font-semibold">Página no encontrada</h1>
                <Link className="mt-4 inline-block text-primary underline" to="/mercado">
                  Volver al Mercado
                </Link>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
export function App() {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
