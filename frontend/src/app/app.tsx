import { useEffect, useRef } from 'react';
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useParams,
} from 'react-router-dom';
import { CircleHelp, FlaskConical, HardDrive, Leaf, UserRound } from 'lucide-react';
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  MarketPage,
  CompanyPage,
  ComparisonPage,
  WatchlistPage,
  MacroPage,
  EventsPage,
  TrackingPage,
} from '@/features/market/index';
import {
  HoldingsPage,
  InvestorPage,
  JournalPage,
  IdeasPage,
  LearnPage,
  PortfolioPage,
  RiskPage,
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
import { useModel } from '@/shared/api/use-model';
import { MODE_SETTING } from '@/shared/ui/research-mode';
import { HomePage } from './home-page';
import { ResearchGate } from './research-gate';
import { CompanySearch } from './company-search';
import {
  companySymbol,
  HELP,
  pageTitle,
  REDIRECTS,
  sectionOf,
  sections as allSections,
} from './navigation';
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
const subLink = ({ isActive }: { isActive: boolean }) =>
  'block shrink-0 rounded-md px-3 py-1.5 text-[13px] transition-colors ' +
  (isActive
    ? 'bg-white/15 font-semibold text-white'
    : 'text-[#c5d8cc] hover:bg-white/10 hover:text-white');
/** «GABI / Sección / Apartado»: where the page sits, with links back up. */
function Breadcrumb({ pathname }: { pathname: string }) {
  const section = sectionOf(pathname);
  const page = section?.pages.find((entry) => entry.path === pathname);
  const symbol = companySymbol(pathname);
  const trail: { label: string; to?: string }[] = [{ label: 'GABI', to: '/' }];
  if (section) trail.push({ label: section.label, to: section.path });
  if (page && page.path !== section?.path) trail.push({ label: page.label });
  if (symbol) trail.push({ label: symbol });
  if (pathname === HELP.path) trail.push({ label: HELP.label });
  else if (!section) trail.push({ label: 'Navegación' });
  return (
    <nav
      aria-label="Ruta"
      className="hidden min-w-0 flex-1 truncate text-xs text-muted-foreground md:block"
    >
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
/** An old route (before #188) sent to its new place, keeping its query and anchor. */
function Redirect({ to }: { to: (params: Record<string, string>) => string }) {
  const params = useParams() as Record<string, string>;
  const { search, hash } = useLocation();
  // The new route may carry its own query (?plan=experimental): the old one is added to it.
  const [path, query = ''] = to(params).split('?');
  const merged = new URLSearchParams(query);
  new URLSearchParams(search).forEach((value, key) => merged.append(key, value));
  const tail = merged.size ? '?' + merged.toString() : '';
  return <Navigate replace to={path + tail + hash} />;
}
function Shell() {
  const location = useLocation();
  const model = useModel();
  const research = model.data?.mode === 'RESEARCH';
  // Investor mode leaves Investigación out of the menus; the backend still blocks its jobs.
  const sections = allSections.filter((item) => research || item.path !== '/investigacion');
  const section = sections.find((item) => item === sectionOf(location.pathname));
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
    // Again once the mode arrives: in Research mode Investigación joins the menu after the first render.
  }, [location.pathname, research]);
  useEffect(() => {
    document.title = pageTitle(location.pathname, location.search);
  }, [location.pathname, location.search]);
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
          {sections.map((item) => (
            <div key={item.path} className="contents lg:block">
              <Link
                to={item.path}
                aria-current={item === section ? 'page' : undefined}
                className={
                  'flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors lg:py-3 ' +
                  (item === section
                    ? // On wide screens its pages are listed below and carry the highlight.
                      'bg-[#dceaca] font-semibold text-[#183e32] lg:bg-transparent lg:text-white'
                    : 'text-[#d5e3da] hover:bg-white/10')
                }
              >
                <item.icon size={18} aria-hidden="true" />
                {item.label}
              </Link>
              {item === section && (
                <ul
                  aria-label={'Apartados de ' + item.label}
                  className="ml-6 mt-1 mb-2 hidden space-y-0.5 border-l border-white/15 pl-2 lg:block"
                >
                  {item.pages.map((sub) => (
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
        {section && (
          <nav
            ref={subNav}
            aria-label="Apartados de la sección"
            className="relative flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden"
          >
            {section.pages.map((sub) => (
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
      <header className="flex h-12 items-center gap-3 border-b bg-card px-4 sm:px-5 lg:h-16 lg:px-9">
        <Breadcrumb pathname={location.pathname} />
        <CompanySearch />
        <div className="flex shrink-0 items-center gap-2">
          <JobsIndicator />
          <Link
            to={HELP.path}
            aria-label="Ayuda y glosario"
            className="inline-flex items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 text-[11px] font-medium hover:bg-accent"
          >
            <CircleHelp size={13} aria-hidden="true" />
            <span className="hidden sm:inline">Ayuda</span>
          </Link>
          {model.data && (
            <Link
              to={MODE_SETTING}
              title="Cambiar de modo en Administración"
              className="inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1 text-[11px] font-medium hover:bg-accent"
            >
              {research ? (
                <FlaskConical size={13} aria-hidden="true" />
              ) : (
                <UserRound size={13} aria-hidden="true" />
              )}
              {/* Icon only on phones; the name stays for screen readers. */}
              <span className="sr-only sm:not-sr-only">
                Modo {research ? 'Research' : 'Investor'}
              </span>
            </Link>
          )}
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
          <Route path="/macro" element={<MacroPage />} />
          <Route path="/eventos" element={<EventsPage />} />
          <Route path="/descubrir" element={<MarketPage />} />
          <Route path="/descubrir/comparar" element={<ComparisonPage />} />
          <Route path="/descubrir/seguidas" element={<WatchlistPage />} />
          <Route path="/empresas/:symbol" element={<CompanyPage />} />
          <Route path="/cartera" element={<PortfolioPage />} />
          <Route path="/cartera/mi-cartera" element={<HoldingsPage />} />
          <Route path="/cartera/perfil" element={<InvestorPage />} />
          <Route path="/cartera/riesgo" element={<RiskPage />} />
          <Route path="/cartera/seguimiento" element={<TrackingPage />} />
          <Route path="/cartera/diario" element={<JournalPage />} />
          <Route path="/cartera/ideas" element={<IdeasPage />} />
          <Route path="/cartera/simuladas" element={<SimulationsPage />} />
          <Route
            path="/investigacion"
            element={
              <ResearchGate>
                <Outlet />
              </ResearchGate>
            }
          >
            <Route index element={<ResearchPage />} />
            <Route path="historico" element={<HistoricalPage />} />
            <Route path="validaciones" element={<BlindValidationsPage />} />
            <Route path="factores" element={<FactorPage />} />
            <Route path="laboratorio" element={<ResearchLabPage />} />
            <Route path="carteras" element={<PortfolioLabPage />} />
          </Route>
          <Route path="/administracion" element={<AdministrationPage />} />
          <Route path="/administracion/calidad" element={<DataHealthPage />} />
          <Route path={HELP.path} element={<LearnPage />} />
          {REDIRECTS.map((redirect) => (
            <Route
              key={redirect.from}
              path={redirect.from}
              element={<Redirect to={redirect.to} />}
            />
          ))}
          <Route
            path="*"
            element={
              <div>
                <h1 className="text-2xl font-semibold">Página no encontrada</h1>
                <Link className="mt-4 inline-block text-primary underline" to="/">
                  Volver a Hoy
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
