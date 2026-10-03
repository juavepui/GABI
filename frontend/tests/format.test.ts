import { describe, expect, it } from 'vitest';
import {
  dateLabel,
  dateText,
  formatCompactMoney,
  formatMoney,
  formatNumber,
  formatPercent,
  metric,
} from '../src/shared/lib/format';

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

describe('large amounts and dates in Spanish', () => {
  it('writes billones and mil M instead of the ambiguous B', () => {
    expect(formatCompactMoney(4.82e12)).toBe('4,82 billones US$');
    expect(formatCompactMoney(6_746_548e6)).toBe('6,75 billones US$');
    expect(formatCompactMoney(14e9)).toBe('14 mil M US$');
    expect(formatCompactMoney(250e6)).toBe('250 M US$');
    expect(formatCompactMoney(-1.5e9)).toBe('-1,5 mil M US$');
    expect(formatCompactMoney(null)).toBe('—');
    expect(metric({ value: 4.82e12, unit: 'USD' }, true)).toBe('4,82 billones US$');
  });

  it('formats ISO dates and timestamps and leaves any other text untouched', () => {
    expect(dateText('2019-01-02')).toBe(dateLabel('2019-01-02'));
    expect(dateText('2026-09-17T13:27:29+02:00')).toBe(dateLabel('2026-09-17'));
    expect(dateText('2019Q1')).toBe('2019Q1');
    expect(dateText(null)).toBe('—');
  });
});
