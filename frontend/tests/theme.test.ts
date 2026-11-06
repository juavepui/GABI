import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { THEME_KEY, applyTheme, readChoice, resolve, saveChoice } from '../src/shared/lib/theme';

function memory(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    removeItem: (key: string) => void values.delete(key),
    values,
  };
}

const broken = {
  getItem: () => {
    throw new Error('blocked');
  },
  setItem: () => {
    throw new Error('blocked');
  },
  removeItem: () => {
    throw new Error('blocked');
  },
};

describe('tema claro, oscuro o automático (#321)', () => {
  it('por defecto es Automático y sigue al sistema', () => {
    expect(readChoice(memory())).toBe('system');
    expect(resolve('system', true)).toBe('dark');
    expect(resolve('system', false)).toBe('light');
    expect(resolve('light', true)).toBe('light');
    expect(resolve('dark', false)).toBe('dark');
  });

  it('recuerda la elección y Automático no deja nada guardado', () => {
    const storage = memory();
    saveChoice('dark', storage);
    expect(storage.values.get(THEME_KEY)).toBe('dark');
    expect(readChoice(storage)).toBe('dark');
    saveChoice('system', storage);
    expect(storage.values.has(THEME_KEY)).toBe(false);
  });

  it('si el almacenamiento falla o tiene basura, usa Automático sin romper', () => {
    expect(readChoice(broken)).toBe('system');
    expect(() => saveChoice('dark', broken)).not.toThrow();
    expect(readChoice(memory({ [THEME_KEY]: 'violeta' }))).toBe('system');
  });

  it('aplica la clase y el esquema de color al documento', () => {
    const root = document.documentElement;
    applyTheme('dark', root);
    expect(root.classList.contains('dark')).toBe(true);
    expect(root.style.colorScheme).toBe('dark');
    applyTheme('light', root);
    expect(root.classList.contains('dark')).toBe(false);
    expect(root.style.colorScheme).toBe('light');
  });
});

describe('sin colores fijos fuera del tema (#321)', () => {
  const SRC = join(__dirname, '..', 'src');
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return name === 'generated' ? [] : files(path);
      return /\.(ts|tsx)$/.test(name) ? [path] : [];
    });
  const PALETTE =
    /(?<![\w-])(?:[a-z-]+:)*(?:bg|text|border|from|to|via|fill|stroke|ring|outline|divide|decoration|accent|shadow)-(?:red|rose|amber|yellow|emerald|green|teal|sky|blue|slate|gray|zinc|neutral|stone|orange|lime|cyan|indigo|violet|purple|pink|fuchsia|white|black)(?:-\d{2,3})?(?:\/\d+)?(?![\w-])/;
  const ARBITRARY = /-\[#[0-9a-fA-F]{3,8}\]/;
  const LITERAL = /['"`]#[0-9a-fA-F]{3,8}['"`]|rgba?\(/;
  // A computed hue is allowed only with its saturation and lightness from the theme.
  const HSL = /hsla?\((?!.*var\(--)/;

  it('los componentes solo usan variables del tema (theme.css)', () => {
    const offenders = files(SRC).flatMap((path) =>
      readFileSync(path, 'utf8')
        .split('\n')
        .map((line, index) => ({ line, index }))
        .filter(
          ({ line }) =>
            PALETTE.test(line) || ARBITRARY.test(line) || LITERAL.test(line) || HSL.test(line),
        )
        .map(({ line, index }) => `${relative(SRC, path)}:${index + 1}: ${line.trim()}`),
    );
    expect(offenders).toEqual([]);
  });
});
