import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

/**
 * The one mould for the cards of «Hoy» (#320): a fixed header (icon, title and «Ver más ›» on the right),
 * then an optional verdict and a few rows. Whoever learns to read one card can read them all.
 */
export function SummaryCard({
  title,
  icon: Icon,
  more,
  verdict,
  children,
  className = '',
  titleExtra,
}: {
  title: string;
  icon?: LucideIcon;
  /** Where «Ver más» goes, and its words when «Ver más» alone would not say where. */
  more?: { to: string; label?: string };
  verdict?: ReactNode;
  children?: ReactNode;
  className?: string;
  /** Something that belongs to the title, such as its glossary term. */
  titleExtra?: ReactNode;
}) {
  return (
    <section aria-label={title} className={'min-w-0 rounded-xl border bg-card p-5 ' + className}>
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          {Icon && <Icon size={20} aria-hidden="true" className="shrink-0 text-muted-foreground" />}
          {title}
          {titleExtra}
        </h2>
        {more && (
          <Link className="text-sm font-medium text-primary hover:underline" to={more.to}>
            {more.label ?? 'Ver más'} <span aria-hidden="true">›</span>
          </Link>
        )}
      </header>
      {verdict != null && <div className="mt-3">{verdict}</div>}
      {children != null && <div className="mt-3">{children}</div>}
    </section>
  );
}
