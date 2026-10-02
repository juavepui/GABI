import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Info } from 'lucide-react';
import { getMetricGlossary } from '@/shared/api/client';

const WIDTH = 288;

/**
 * A technical term with an ⓘ button that shows its definition (from the backend glossary) and a link
 * to the full glossary in Aprender. The live region only exists while the hint is open, so pages with
 * many terms do not carry empty status regions.
 */
export function Term({ k, children }: { k: string; children: ReactNode }) {
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const open = position !== null;
  const glossary = useQuery({
    queryKey: ['learn', 'metrics'],
    queryFn: ({ signal }) => getMetricGlossary(signal),
    staleTime: Infinity,
    enabled: open,
  });
  const entry = glossary.data?.glossary.find((item) => item.key === k);
  const name = typeof children === 'string' ? children : (entry?.term ?? k);

  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent && event.key !== 'Escape') return;
      if (event.type === 'mousedown' && button.current?.contains(event.target as Node)) return;
      if (event.type === 'mousedown' && (event.target as Element).closest?.('[data-term-tip]'))
        return;
      setPosition(null);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  function toggle() {
    if (open || !button.current) {
      setPosition(null);
      return;
    }
    // Fixed position: the hint must not be clipped by scrolling tables.
    const rect = button.current.getBoundingClientRect();
    setPosition({
      left: Math.max(8, Math.min(rect.left - 12, window.innerWidth - WIDTH - 8)),
      top: rect.bottom + 6,
    });
  }

  return (
    <span className="inline-flex items-center gap-1">
      {children}
      <button
        ref={button}
        type="button"
        aria-label={'Qué es ' + name}
        aria-expanded={open}
        aria-controls={id}
        onClick={toggle}
        className="inline-grid size-4 shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <Info size={13} aria-hidden="true" />
      </button>
      {position && (
        <span id={id} role="status" aria-live="polite">
          <span
            data-term-tip
            style={{ left: position.left, top: position.top, width: WIDTH }}
            className="fixed z-50 block rounded-lg border bg-card p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground shadow-lg"
          >
            <span className="block font-semibold">{entry?.term ?? name}</span>
            <span className="mt-1 block text-muted-foreground">
              {glossary.isPending ? 'Cargando…' : (entry?.definition ?? 'Sin definición.')}
            </span>
            <Link
              to={'/cartera/aprender?tab=glosario#termino-' + k}
              className="mt-2 inline-block font-medium text-primary underline"
              onClick={() => setPosition(null)}
            >
              Más en Aprender
            </Link>
          </span>
        </span>
      )}
    </span>
  );
}
