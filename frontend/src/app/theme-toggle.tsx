import { useEffect, useState } from 'react';
import { Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';
import { applyTheme, readChoice, resolve, saveChoice, type ThemeChoice } from '@/shared/lib/theme';

const OPTIONS: { value: ThemeChoice; label: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Claro', icon: Sun },
  { value: 'dark', label: 'Oscuro', icon: Moon },
  { value: 'system', label: 'Automático (el del sistema)', icon: Monitor },
];

function systemDark(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );
}

/** Claro / Oscuro / Automático in the header (#321). Automático follows the system live. */
export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(() => readChoice());

  useEffect(() => {
    applyTheme(resolve(choice, systemDark()));
    if (choice !== 'system' || typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const follow = () => applyTheme(resolve('system', media.matches));
    media.addEventListener('change', follow);
    return () => media.removeEventListener('change', follow);
  }, [choice]);

  const choose = (value: ThemeChoice) => {
    saveChoice(value);
    setChoice(value);
  };

  return (
    <div
      role="radiogroup"
      aria-label="Tema de la pantalla"
      className="inline-flex items-center rounded-full border bg-background p-0.5"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = choice === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            tabIndex={active ? 0 : -1}
            onClick={() => choose(value)}
            onKeyDown={(event) => {
              const step =
                event.key === 'ArrowRight' || event.key === 'ArrowDown'
                  ? 1
                  : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
                    ? -1
                    : 0;
              if (!step) return;
              event.preventDefault();
              const index =
                (OPTIONS.findIndex((option) => option.value === choice) + step + OPTIONS.length) %
                OPTIONS.length;
              choose(OPTIONS[index].value);
              const group = event.currentTarget.parentElement;
              (group?.children[index] as HTMLElement | undefined)?.focus();
            }}
            className={
              'inline-flex size-6 items-center justify-center rounded-full ' +
              (active
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent')
            }
          >
            <Icon size={13} aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
