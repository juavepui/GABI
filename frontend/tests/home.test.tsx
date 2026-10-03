import { afterEach, describe, expect, it, vi } from 'vitest';
import type { HomeResponse } from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({ getHome: vi.fn(), getNotices: vi.fn() }));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  getHome: api.getHome,
  getNotices: api.getNotices,
}));
const { HomePage } = await import('../src/app/home-page');
const { ApiError } = await import('../src/shared/api/client');

function home(data: Partial<NonNullable<HomeResponse['data']>> | null): HomeResponse {
  return {
    as_of: '2026-10-03',
    model_id: 'GABI-MF-v1',
    ranking_ready: data !== null,
    data: data && {
      status: 'ready',
      universe_count: 503,
      prices_available: 503,
      fundamentals_available: 503,
      sec_available: 503,
      scored_count: 501,
      latest_price_date: '2026-09-30',
      warnings: [],
      last_session: '2026-10-02',
      prices_current: false,
      ...data,
    },
    target: [],
    target_positions: 20,
    last_update: null,
    steps: { fred_key: true, universe: true, data_loaded: data !== null, updated: false },
  };
}

const NOTICES = { blind_available: true, blind_rebalances: [], smallmid: null };
let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

describe('Inicio: estado de los datos', () => {
  it('dice «Al día» solo cuando el backend confirma el último cierre', async () => {
    api.getNotices.mockResolvedValue(NOTICES);
    api.getHome.mockResolvedValue(home({ prices_current: true, last_session: '2026-09-30' }));
    screen = renderScreen(<HomePage />);
    await screen.findText('Al día');
    expect(screen.text()).not.toContain('Falta el último cierre');
  });

  it('avisa de la sesión que falta en vez de decir «Al día»', async () => {
    api.getNotices.mockResolvedValue(NOTICES);
    api.getHome.mockResolvedValue(home({ prices_current: false }));
    screen = renderScreen(<HomePage />);
    await screen.findText('Falta el último cierre');
    expect(screen.text()).toContain('Última sesión cerrada en NYSE: 02 oct 2026');
    expect(screen.text()).not.toContain('Al día');
  });

  it('muestra los datos antiguos y sus motivos', async () => {
    api.getNotices.mockResolvedValue(NOTICES);
    api.getHome.mockResolvedValue(home({ status: 'stale', warnings: ['prices_stale'] }));
    screen = renderScreen(<HomePage />);
    await screen.findText('Con datos antiguos');
    expect(screen.text()).toContain('hay precios de hace más de 7 días');
  });

  it('calcula el ranking cuando aún no está en caché', async () => {
    api.getNotices.mockResolvedValue(NOTICES);
    api.getHome.mockImplementation((compute: boolean) =>
      compute ? new Promise(() => {}) : Promise.resolve(home(null)),
    );
    screen = renderScreen(<HomePage />);
    await screen.findText('Calculando el ranking con tu caché local');
    expect(api.getHome).toHaveBeenCalledWith(true, expect.anything());
  });

  it('enseña el error de la API con un botón para reintentar', async () => {
    api.getNotices.mockResolvedValue(NOTICES);
    api.getHome.mockRejectedValue(new ApiError(500, 'internal', 'La caché local no responde.'));
    screen = renderScreen(<HomePage />);
    await screen.findText('No se pueden cargar los datos');
    expect(screen.text()).toContain('La caché local no responde.');
    expect(screen.text()).toContain('Reintentar');
  });
});
