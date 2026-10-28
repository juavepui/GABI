import { afterEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_COLUMNS,
  exportHref,
  loadPreferences,
  savePreferences,
  visibleColumns,
} from '../src/features/market/ranking-columns';

const KEY = 'gabi.ranking.preferences.v1';
afterEach(() => localStorage.clear());

describe('Preferencias del Ranking (#196)', () => {
  it('sin preferencias o con datos ilegibles usa las columnas por defecto', () => {
    expect(loadPreferences()).toEqual({ columns: DEFAULT_COLUMNS, query: '' });
    localStorage.setItem(KEY, '{no es json');
    expect(loadPreferences()).toEqual({ columns: DEFAULT_COLUMNS, query: '' });
    localStorage.setItem(KEY, '42');
    expect(loadPreferences()).toEqual({ columns: DEFAULT_COLUMNS, query: '' });
  });

  it('descarta columnas desconocidas y parámetros que no son preferencias', () => {
    localStorage.setItem(
      KEY,
      JSON.stringify({
        columns: ['roe', 'composite_score', '<script>', 7, 'next_earnings'],
        query: 'order_by=roe&offset=50&value=0.4&exclude_sectors=Energy&limit=50',
      }),
    );
    expect(loadPreferences()).toEqual({
      columns: ['roe', 'next_earnings'],
      query: 'order_by=roe&exclude_sectors=Energy&limit=50',
    });
  });

  it('guarda y recupera lo elegido', () => {
    savePreferences({ columns: ['volatility'], query: 'earnings=exclude&earnings_days=10' });
    expect(loadPreferences()).toEqual({
      columns: ['volatility'],
      query: 'earnings=exclude&earnings_days=10',
    });
  });

  it('el CSV pide la vista entera con las columnas visibles, en el orden de la tabla', () => {
    const href = exportHref(
      new URLSearchParams('order_by=roe&offset=25&limit=25&value=0.4'),
      visibleColumns(['next_earnings', 'roe']),
    );
    const url = new URL(href, 'http://localhost');
    expect(url.pathname).toBe('/api/v1/ranking/export.csv');
    expect(url.searchParams.get('offset')).toBeNull();
    expect(url.searchParams.get('limit')).toBeNull();
    // Experimental weights stay: the CSV is the same calculation as the table.
    expect(url.searchParams.get('value')).toBe('0.4');
    expect(url.searchParams.getAll('columns')).toEqual([
      'composite_score',
      'roe',
      'next_earnings_date',
      'next_earnings_days',
    ]);
  });
});
