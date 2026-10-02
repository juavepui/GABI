import type { ReactNode } from 'react';

/** A methodology note folded under «Cómo leer esto», so results come first and the explanation stays one click away. */
export function HowToRead({
  children,
  title = 'Cómo leer esto',
  className = '',
}: {
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <details className={'text-xs text-muted-foreground ' + className}>
      <summary className="cursor-pointer font-medium text-primary">{title}</summary>
      <p className="mt-1 max-w-3xl leading-relaxed">{children}</p>
    </details>
  );
}
