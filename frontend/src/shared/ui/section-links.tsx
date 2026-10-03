import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ChevronRight, type LucideIcon } from 'lucide-react';

export type SectionLink = {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
};

/** The sub-sections of a page as buttons with an icon and one line of context, in the app's palette. */
export function SectionLinks({ links, label }: { links: SectionLink[]; label: string }) {
  return (
    <nav aria-label={label} className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {links.map(({ to, label: title, description, icon: Icon }) => (
        <Link
          key={to}
          to={to}
          className={
            'group flex items-center gap-3 rounded-xl border p-3.5 shadow-sm transition-all ' +
            'hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 ' +
            'focus-visible:ring-primary border-border bg-card hover:border-primary/40 hover:bg-accent'
          }
        >
          <span
            className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-primary"
            aria-hidden="true"
          >
            <Icon size={20} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-semibold text-foreground">{title}</span>
            <span className="block text-xs leading-snug text-muted-foreground">{description}</span>
          </span>
          <ChevronRight
            size={18}
            aria-hidden="true"
            className="shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
          />
        </Link>
      ))}
    </nav>
  );
}

/** «Back to the parent section» as a pill button. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-accent px-3 py-1 text-sm font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <ArrowLeft size={15} aria-hidden="true" />
      {children}
    </Link>
  );
}
