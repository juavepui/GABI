import type { ReactNode } from 'react';
import { BackLink } from './section-links';

/** The header every page shares: back link, eyebrow, title, one line, a folded guide, actions and extras. */
export function PageHeader({
  back,
  eyebrow,
  title,
  description,
  guide,
  actions,
  children,
}: {
  back?: { to: string; label: string };
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  /** The full explanation, folded under «Cómo leer esta página» so one line stays visible. */
  guide?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header>
      {back && (
        <div className="mb-3">
          <BackLink to={back.to}>{back.label}</BackLink>
        </div>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && (
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
              {eyebrow}
            </p>
          )}
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          {description && (
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
              {description}
            </p>
          )}
          {guide && (
            <details className="mt-2 max-w-3xl text-sm">
              <summary className="cursor-pointer text-xs font-medium text-primary">
                Cómo leer esta página
              </summary>
              <div className="mt-2 space-y-2 leading-relaxed text-muted-foreground">{guide}</div>
            </details>
          )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}
