import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { BookOpen, X } from 'lucide-react';

const OPENED = 'gabi:how-to-read';

/**
 * An explanation behind a button, in a side panel that does not move the page (#320): results come first and
 * the method stays one click away. One panel at a time; Escape or «Cerrar» closes it and focus returns to the
 * button. The text stays in the page while closed, so search and screen readers can still reach it.
 */
export function SidePanelNote({
  title,
  children,
  className = '',
  buttonClassName = 'text-xs font-medium text-primary',
}: {
  title: string;
  children: ReactNode;
  className?: string;
  buttonClassName?: string;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const other = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== id) setOpen(false);
    };
    window.addEventListener(OPENED, other);
    return () => window.removeEventListener(OPENED, other);
  }, [id]);
  useEffect(() => {
    if (!open) return;
    window.dispatchEvent(new CustomEvent(OPENED, { detail: id }));
    panel.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      button.current?.focus();
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [open, id]);
  function close() {
    setOpen(false);
    button.current?.focus();
  }
  return (
    <div className={className}>
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => (open ? close() : setOpen(true))}
        className={
          'inline-flex cursor-pointer items-center gap-1 text-left hover:underline ' +
          buttonClassName
        }
      >
        <BookOpen size={14} aria-hidden="true" className="shrink-0" />
        {title}
      </button>
      <aside
        id={id}
        ref={panel}
        tabIndex={-1}
        hidden={!open}
        aria-label={title}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l bg-card text-card-foreground shadow-2xl focus:outline-none"
      >
        <div className="flex items-center gap-3 border-b px-5 py-3">
          {open && <p className="text-base font-semibold">{title}</p>}
          <button
            type="button"
            onClick={close}
            className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm hover:bg-muted"
          >
            <X size={16} aria-hidden="true" />
            Cerrar
          </button>
        </div>
        <div className="space-y-2 overflow-y-auto px-5 py-4 text-sm leading-relaxed text-muted-foreground">
          {children}
        </div>
      </aside>
    </div>
  );
}

/** A methodology note behind «Cómo leer esto», shown in the side panel. */
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
    <SidePanelNote title={title} className={className}>
      {children}
    </SidePanelNote>
  );
}
