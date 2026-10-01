import { useId, useMemo, useState, type KeyboardEvent } from 'react';
import { Search, X } from 'lucide-react';

export type CompanyOption = { symbol: string; name: string | null };

const MAX_SHOWN = 30;

function normalize(text: string) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

/** Search a company by symbol or name, anywhere in the text; arrows and Enter choose, Escape closes. */
export function CompanyPicker({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: CompanyOption[];
  value: string;
  onChange: (symbol: string) => void;
}) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const selected = options.find((option) => option.symbol === value);
  const matches = useMemo(() => {
    const text = normalize(query.trim());
    if (!text) return options.slice(0, MAX_SHOWN);
    const ranked = options
      .map((option) => {
        const symbol = normalize(option.symbol);
        const name = normalize(option.name ?? '');
        const rank =
          symbol === text ? 0 : symbol.startsWith(text) ? 1 : name.startsWith(text) ? 2 : 3;
        return { option, rank, hit: symbol.includes(text) || name.includes(text) };
      })
      .filter((item) => item.hit)
      .sort((a, b) => a.rank - b.rank || a.option.symbol.localeCompare(b.option.symbol));
    return ranked.slice(0, MAX_SHOWN).map((item) => item.option);
  }, [options, query]);

  function choose(symbol: string) {
    onChange(symbol);
    setQuery('');
    setOpen(false);
  }

  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
      setActive((index) => Math.min(index + 1, matches.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === 'Enter' && open && matches[active]) {
      event.preventDefault();
      choose(matches[active].symbol);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div className="relative text-xs font-medium">
      <label htmlFor={id}>{label}</label>
      {selected && !open ? (
        <div className="mt-1.5 flex h-10 items-center justify-between gap-2 rounded-md border border-primary/30 bg-accent px-3 text-sm">
          <button
            type="button"
            className="min-w-0 truncate text-left font-medium"
            onClick={() => setOpen(true)}
            id={id}
          >
            {selected.symbol}
            <span className="ml-1.5 font-normal text-muted-foreground">{selected.name}</span>
          </button>
          <button
            type="button"
            aria-label={'Quitar ' + selected.symbol}
            className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
            onClick={() => onChange('')}
          >
            <X size={15} />
          </button>
        </div>
      ) : (
        <div className="relative mt-1.5">
          <Search
            size={15}
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-controls={id + '-list'}
            aria-autocomplete="list"
            aria-activedescendant={open && matches[active] ? id + '-' + active : undefined}
            autoComplete="off"
            placeholder="Busca por símbolo o nombre"
            className="h-10 w-full rounded-md border bg-background pl-8 pr-2 text-sm font-normal"
            value={query}
            autoFocus={open && Boolean(selected)}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => window.setTimeout(() => setOpen(false), 150)}
            onKeyDown={onKey}
          />
        </div>
      )}
      {open && (
        <ul
          id={id + '-list'}
          role="listbox"
          aria-label={label}
          className="absolute z-20 mt-1 max-h-72 w-full min-w-64 overflow-y-auto rounded-md border bg-card py-1 text-sm font-normal shadow-lg"
        >
          {matches.length === 0 && (
            <li className="px-3 py-2 text-muted-foreground">Ninguna empresa coincide.</li>
          )}
          {matches.map((option, index) => (
            <li
              key={option.symbol}
              id={id + '-' + index}
              role="option"
              aria-selected={index === active}
              className={
                'flex cursor-pointer gap-2 px-3 py-1.5 ' +
                (index === active ? 'bg-accent text-foreground' : 'hover:bg-muted')
              }
              onMouseDown={(event) => {
                event.preventDefault();
                choose(option.symbol);
              }}
              onMouseEnter={() => setActive(index)}
            >
              <span className="w-14 shrink-0 font-semibold">{option.symbol}</span>
              <span className="truncate text-muted-foreground">{option.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
