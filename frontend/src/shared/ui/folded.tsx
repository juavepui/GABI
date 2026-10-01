import { useState, type ReactNode } from 'react';

/** A collapsed section whose content (and its queries) mounts only once it is opened. */
export function Folded({
  title,
  className = 'rounded-xl border bg-card p-5 text-sm',
  children,
}: {
  title: string;
  className?: string;
  children: ReactNode;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      className={className}
      onToggle={(event) => event.currentTarget.open && setOpened(true)}
    >
      <summary className="cursor-pointer font-medium">{title}</summary>
      {opened && <div className="mt-3 space-y-3">{children}</div>}
    </details>
  );
}
