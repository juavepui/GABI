import { useEffect, useRef } from 'react';
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  Link,
} from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  ChartNoAxesCombined,
  BriefcaseBusiness,
  FlaskConical,
  Settings2,
  ArrowUpRight,
  HardDrive,
  Leaf,
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
import { ResearchPage } from '@/features/research/index';
import { AdministrationPage } from '@/features/administration/index';
import { ApiError } from '@/shared/api/client';

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 300_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status === 409),
    },
  },
});
const navigation = [
  { path: '/cartera', label: 'Cartera', icon: BriefcaseBusiness },
  { path: '/mercado', label: 'Mercado', icon: ChartNoAxesCombined },
  { path: '/investigacion', label: 'Investigación', icon: FlaskConical },
  { path: '/administracion', label: 'Administración', icon: Settings2 },
];
function Shell() {
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  const previous = useRef(location.pathname);
  useEffect(() => {
    if (previous.current !== location.pathname) {
      previous.current = location.pathname;
      main.current?.focus();
      window.scrollTo(0, 0);
    }
  }, [location.pathname]);
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
          to="/mercado"
          aria-label="GABI, inicio de Mercado"
          className="flex items-center gap-3 px-5 py-5 lg:px-7 lg:py-8"
        >
          <span className="flex size-10 items-center justify-center rounded-xl bg-white/10">
            <Leaf size={24} aria-hidden="true" />
          </span>
          <span>
            <span className="block text-xl font-semibold tracking-[0.14em]">GABI</span>
            <span className="block text-[11px] tracking-wide text-[#c5d8cc]">
              Análisis con evidencia
            </span>
          </span>
        </Link>
        <p className="hidden px-7 pb-3 text-[10px] uppercase tracking-[0.18em] text-[#b7cebf] lg:block">
          Espacio de trabajo
        </p>
        <nav
          aria-label="Navegación principal"
          className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:px-4"
        >
          {navigation.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                'flex shrink-0 items-center gap-3 rounded-lg px-3 py-3 text-sm transition-colors ' +
                (isActive
                  ? 'bg-[#dceaca] font-semibold text-[#183e32]'
                  : 'text-[#d5e3da] hover:bg-white/10')
              }
            >
              <item.icon size={18} aria-hidden="true" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden px-5 pb-6 lg:block">
          <div className="rounded-xl border border-white/15 bg-white/5 p-4">
            <p className="flex items-center gap-2 text-xs font-medium">
              <HardDrive size={14} aria-hidden="true" />
              Tu instalación local
            </p>
            <p className="mt-2 text-[11px] leading-relaxed text-[#c5d8cc]">
              Datos y cálculos permanecen en este equipo.
            </p>
            <a
              href="http://localhost:8501"
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex items-center gap-1 text-xs font-medium"
            >
              Abrir Streamlit <ArrowUpRight size={14} aria-hidden="true" />
            </a>
          </div>
        </div>
      </aside>
      <header className="flex h-16 items-center justify-between gap-3 border-b bg-card px-5 lg:px-9">
        <p className="text-xs text-muted-foreground">
          GABI <span className="mx-2 text-border">/</span>{' '}
          {navigation.find((item) => location.pathname.startsWith(item.path))?.label ??
            'Navegación'}
        </p>
        <span className="inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-[11px] font-medium">
          <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
          Entorno local
        </span>
      </header>
      <main
        id="contenido"
        ref={main}
        tabIndex={-1}
        className="mx-auto max-w-[1480px] px-4 py-7 focus:outline-none sm:px-6 lg:px-9 lg:py-9"
      >
        <Routes>
          <Route path="/" element={<Navigate to="/mercado" replace />} />
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
          <Route path="/administracion" element={<AdministrationPage />} />
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
