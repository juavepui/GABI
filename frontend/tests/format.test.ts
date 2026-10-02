import { describe, expect, it } from 'vitest';
import { formatMoney, formatNumber, formatPercent } from '../src/shared/lib/format';

const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');

describe('shared number formatting', () => {
  it('uses Spanish separators and «—» for an absent value', () => {
    expect(formatNumber(1234.5)).toBe('1234,5');
    expect(formatNumber(12345.678, { digits: 1 })).toBe('12.345,7');
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(undefined)).toBe('—');
    expect(formatNumber(Number.NaN)).toBe('—');
  });

  it('fixes decimals and the sign only when asked', () => {
    expect(formatNumber(0.5, { digits: 2, fixed: true })).toBe('0,50');
    expect(formatNumber(0.5, { digits: 2 })).toBe('0,5');
    expect(formatNumber(1.5, { digits: 1, signed: true })).toBe('+1,5');
  });

  it('shows fractions as percentages, as the Research Lab drawdown', () => {
    expect(formatPercent(-0.21, { digits: 1, fixed: true })).toBe('-21,0 %');
    expect(formatPercent(0.091)).toBe('9,1 %');
    expect(formatPercent(null)).toBe('—');
  });

  it('formats money with the currency', () => {
    expect(plain(formatMoney(1500))).toBe('1500 US$');
    expect(plain(formatMoney(2500.5, { currency: 'EUR', digits: 2 }))).toBe('2500,50 €');
  });
});
