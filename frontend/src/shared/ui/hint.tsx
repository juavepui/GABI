import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

const WIDTH = 320;

/**
 * A label that explains itself on hover or keyboard focus. The explanation is always in the
 * accessibility tree as the trigger's description; it is only drawn while hovered or focused.
 * Fixed position, so tables that scroll horizontally do not clip it.
 */
export function Hint({ children, content }: { children: ReactNode; content: ReactNode }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  useEffect(() => {
    if (!position) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent && event.key !== 'Escape') return;
      setPosition(null);
    };
    document.addEventListener('keydown', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('keydown', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [position]);

  function show() {
    if (!trigger.current) return;
    const rect = trigger.current.getBoundingClientRect();
    setPosition({
      left: Math.max(8, Math.min(rect.left, window.innerWidth - WIDTH - 8)),
      top: rect.bottom + 6,
    });
  }

  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-describedby={id}
        onMouseEnter={show}
        onMouseLeave={() => setPosition(null)}
        onFocus={show}
        onBlur={() => setPosition(null)}
        className="cursor-help text-left underline decoration-dotted decoration-muted-foreground underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {children}
      </button>
      <span
        id={id}
        role="tooltip"
        hidden={!position}
        style={position ? { left: position.left, top: position.top, width: WIDTH } : undefined}
        className="fixed z-50 block rounded-lg border bg-card p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground shadow-lg"
      >
        {content}
      </span>
    </>
  );
}
