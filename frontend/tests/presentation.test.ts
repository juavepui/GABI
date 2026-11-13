import { describe, expect, it, vi } from 'vitest';
import { metric, dateLabel } from '../src/shared/lib/format';
import { rankingParams, patchParams } from '../src/features/market/params';
import { ApiError, getCompany, getRanking } from '../src/shared/api/client';

describe('units and absence from the contract', () => {
  it('formats fractions, percentages, dollars and missing data without substituting zero', () => {
    expect(metric({ value: 0.123, unit: 'fraction' })).toBe('12,3 %');
    expect(metric({ value: 12.3, unit: 'percent' })).toBe('12,3 %');
    expect(metric({ value: 12.3, unit: 'points_0_100' })).toBe('12,3');
    expect(metric({ value: null, unit: 'USD' })).toBe('—');
    expect(metric(undefined)).toBe('—');
    expect(metric({ value: 0, unit: 'count' })).toBe('0');
    expect(metric({ value: 14e9, unit: 'USD' }, true)).not.toMatch(/[\u00a0\u202f]/);
    expect(dateLabel('invalid')).toBe('Sin fecha');
    expect(dateLabel('2026-09-29')).toContain('29');
  });
});
describe('URL state', () => {
  it('round-trips multiple sectors, pagination and sorting; filter changes reset the page', () => {
    const original = new URLSearchParams(
      'offset=25&limit=25&order_by=market_cap&direction=asc&sectors=A&sectors=B&hide_no_data=false',
    );
    const query = rankingParams(original);
    expect(query).toMatchObject({
      sectors: ['A', 'B'],
      offset: 25,
      direction: 'asc',
      hide_no_data: false,
    });
    const next = patchParams(original, { search: 'BRK', sectors: ['B', 'C'] });
    expect(rankingParams(next)).toMatchObject({
      search: 'BRK',
      sectors: ['B', 'C'],
      offset: 0,
      order_by: 'market_cap',
    });
    expect(original.get('offset')).toBe('25');
    expect(patchParams(original, { bars: '63' }, false).get('offset')).toBe('25');
  });
  it('normalizes malformed navigation to valid request parameters', () => {
    expect(
      rankingParams(
        new URLSearchParams('offset=-1&limit=NaN&order_by=bad&min_market_cap=Infinity'),
      ),
    ).toMatchObject({ offset: 0, limit: 25, order_by: 'composite_score', min_market_cap: 0 });
  });
});
describe('HTTP boundary', () => {
  it('encodes symbols and repeated sectors, and propagates cancellation to fetch', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}'));
    const signal = new AbortController().signal;
    await getRanking({ sectors: ['A', 'B'], search: 'x&y' }, signal);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/ranking?sectors=A&sectors=B&search=x%26y',
      expect.objectContaining({ signal }),
    );
    fetchMock.mockResolvedValueOnce(new Response('{}'));
    await getCompany('BRK-B', 63, signal);
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/companies/BRK-B?bars=63',
      expect.objectContaining({ signal }),
    );
  });
  it('preserves sanitized API errors and hides unexpected proxy bodies', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: { code: 'DATA_CHANGED', message: 'Datos modificados' } }),
          { status: 409 },
        ),
      );
    await expect(getRanking({})).rejects.toMatchObject({
      status: 409,
      code: 'DATA_CHANGED',
      message: 'Datos modificados',
    });
    fetchMock.mockResolvedValueOnce(new Response('<html>internal proxy</html>', { status: 502 }));
    await expect(getRanking({})).rejects.toEqual(
      new ApiError(502, 'HTTP_ERROR', 'No se ha podido consultar la API local.'),
    );
  });
  it('does not convert aborted requests to success or user data', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new DOMException('Aborted', 'AbortError'));
    await expect(getRanking({}, new AbortController().signal)).rejects.toMatchObject({
      name: 'AbortError',
    });
  });
});
