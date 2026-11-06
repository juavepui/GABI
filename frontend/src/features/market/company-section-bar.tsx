import { useEffect, useRef, useState, type RefObject } from 'react';
import type { Tone } from '@/shared/ui/tone';
import { TONE_STYLE } from '@/shared/ui/tone';

export type CompanySection = { id: string; label: string };

/**
 * The ficha's bar that stays at the top while scrolling (#320): the company, its score and verdict in words, and
 * tabs to each section, marking the one on screen. The name and score only appear once the page header has
 * scrolled away, so they are never shown twice.
 */
export function CompanySectionBar({
  symbol,
  name,
  score,
  verdict,
  tone,
  sections,
  header,
}: {
  symbol: string;
  name: string;
  score: string | null;
  verdict: string;
  tone: Tone;
  sections: CompanySection[];
  /** The page header: while it is visible the bar shows only the tabs. */
  header: RefObject<HTMLElement | null>;
}) {
  const [stuck, setStuck] = useState(false);
  const [current, setCurrent] = useState(sections[0]?.id);
  const visible = useRef(new Map<string, boolean>());
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined' || !header.current) return;
    const observer = new IntersectionObserver(([entry]) => setStuck(!entry.isIntersecting));
    observer.observe(header.current);
    return () => observer.disconnect();
  }, [header]);
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const seen = visible.current;
    // A section counts as «on screen» while it crosses the upper part of the window.
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => seen.set(entry.target.id, entry.isIntersecting));
        const first = sections.find((section) => seen.get(section.id));
        if (first) setCurrent(first.id);
      },
      { rootMargin: '-80px 0px -55% 0px' },
    );
    sections.forEach((section) => {
      const element = document.getElementById(section.id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [sections]);
  const Icon = TONE_STYLE[tone].icon;
  return (
    <nav
      aria-label={'Secciones de la ficha de ' + symbol}
      className="sticky top-0 z-30 -mx-4 mb-6 border-b bg-background/95 px-4 py-2 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-9 lg:px-9"
    >
      {/* One row whose height the tabs set: showing the name never moves the page (a moving page would
          close any open hint and shift what the reader is looking at). */}
      <div className="flex items-center gap-4">
        {stuck && (
          <p className="hidden min-w-0 shrink items-center gap-x-2 text-sm md:flex">
            <span className="font-semibold">{symbol}</span>
            <span className="hidden truncate text-muted-foreground xl:inline">{name}</span>
            <span
              className={
                'inline-flex shrink-0 items-center gap-1 font-medium ' + TONE_STYLE[tone].ink
              }
            >
              <Icon size={14} aria-hidden="true" />
              {verdict}
              {score && <span className="tabular-nums"> · {score}</span>}
            </span>
          </p>
        )}
        <ul className="flex min-w-0 gap-1 overflow-x-auto text-sm">
          {sections.map((section) => (
            <li key={section.id} className="shrink-0">
              <a
                href={'#' + section.id}
                aria-current={current === section.id ? 'location' : undefined}
                className={
                  'block whitespace-nowrap rounded-md px-3 py-1.5 hover:bg-muted ' +
                  (current === section.id
                    ? 'bg-secondary font-medium text-secondary-foreground'
                    : 'text-muted-foreground')
                }
              >
                {section.label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
