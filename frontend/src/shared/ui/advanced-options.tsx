import { useState, type ReactNode } from 'react';
import { CircleHelp } from 'lucide-react';
import { Hint } from './hint';

const KEY = 'gabi.advanced.';

function remembered(id: string): boolean {
  try {
    return window.localStorage.getItem(KEY + id) === 'open';
  } catch {
    return false; // Storage blocked: start folded.
  }
}

function remember(id: string, open: boolean) {
  try {
    window.localStorage.setItem(KEY + id, open ? 'open' : 'closed');
  } catch {
    // A preference only; the form works the same without it.
  }
}

/** «Opciones avanzadas» (#190): the fields most uses leave at their default, folded. Whether it was
 *  left open is remembered per form in this browser. */
export function AdvancedOptions({
  id,
  children,
  className = '',
}: {
  id: string;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(() => remembered(id));
  return (
    <details
      className={'rounded-lg border p-3 text-sm ' + className}
      open={open}
      onToggle={(event) => {
        const next = event.currentTarget.open;
        setOpen(next);
        remember(id, next);
      }}
    >
      <summary className="cursor-pointer font-medium">Opciones avanzadas</summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

/** A labelled field with its help on hover or focus: unit and effect. The help button sits next to
 *  the label, never inside it, so the label still names the input (`htmlFor` = the input's id). */
export function HelpField({
  id,
  label,
  help,
  children,
  className = 'text-sm',
}: {
  id: string;
  label: string;
  help: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="flex items-center gap-1">
        <label htmlFor={id}>{label}</label>
        <Hint content={help}>
          <CircleHelp size={14} aria-hidden="true" className="text-muted-foreground" />
          <span className="sr-only">Ayuda: {label}</span>
        </Hint>
      </div>
      {children}
    </div>
  );
}
