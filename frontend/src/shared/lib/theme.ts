/**
 * Theme choice (#321): Claro, Oscuro or Automático (the system's, the default). The choice lives in this
 * browser only; if storage is unavailable, Automático is used and nothing breaks. `index.html` applies the
 * same rule before the first paint, so keep `THEME_KEY` and the class in sync with it.
 */
export type ThemeChoice = 'light' | 'dark' | 'system';
export type Theme = 'light' | 'dark';

export const THEME_KEY = 'gabi-theme';
const CHOICES: ThemeChoice[] = ['light', 'dark', 'system'];

export function readChoice(
  storage: Pick<Storage, 'getItem'> | undefined = safeStorage(),
): ThemeChoice {
  try {
    const value = storage?.getItem(THEME_KEY);
    return CHOICES.includes(value as ThemeChoice) ? (value as ThemeChoice) : 'system';
  } catch {
    return 'system';
  }
}

export function saveChoice(
  choice: ThemeChoice,
  storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined = safeStorage(),
): void {
  try {
    if (choice === 'system') storage?.removeItem(THEME_KEY);
    else storage?.setItem(THEME_KEY, choice);
  } catch {
    // Private window or blocked storage: the choice lasts until the page is reloaded.
  }
}

export function resolve(choice: ThemeChoice, systemDark: boolean): Theme {
  return choice === 'system' ? (systemDark ? 'dark' : 'light') : choice;
}

export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
  // The browser bar takes the sidebar colour of the theme just applied.
  const bar = getComputedStyle(root).getPropertyValue('--sidebar').trim();
  if (bar)
    root.ownerDocument.querySelector('meta[name="theme-color"]')?.setAttribute('content', bar);
}

function safeStorage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}
