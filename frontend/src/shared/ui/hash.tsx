import { Fragment, useState } from 'react';
import { Check, Copy } from 'lucide-react';

const SHOWN = 8;
// SHA-1/SHA-256 digests (40–64 hex characters) inside free text such as experiment notes.
const DIGEST = /\b[0-9a-f]{40,64}\b/g;

/** A digest shortened to 8 characters; the full value is in the tooltip and one click copies it.
 *  `copy={false}` inside another control (a <summary>), where a button cannot be nested. */
export function Hash({ value, copy = true }: { value: string; copy?: boolean }) {
  const [copied, setCopied] = useState(false);
  if (value.length <= SHOWN + 4) return <code className="font-mono">{value}</code>;
  if (!copy)
    return (
      <code className="font-mono" title={value}>
        {value.slice(0, SHOWN)}…
      </code>
    );
  return (
    <span className="inline-flex items-center gap-0.5 align-baseline">
      <code className="font-mono" title={value}>
        {value.slice(0, SHOWN)}…
      </code>
      <button
        type="button"
        className="inline-flex rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        title={copied ? 'Copiado' : 'Copiar el valor completo'}
        aria-label={(copied ? 'Copiado: ' : 'Copiar ') + value}
        onClick={() => void navigator.clipboard?.writeText(value).then(() => setCopied(true))}
      >
        {copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
      </button>
    </span>
  );
}

/** Free text with every digest in it shortened by {@link Hash}. */
export function HashText({ text, copy = true }: { text: string; copy?: boolean }) {
  const parts = text.split(DIGEST);
  const digests = text.match(DIGEST) ?? [];
  return (
    <>
      {parts.map((part, index) => (
        <Fragment key={index}>
          {part}
          {index < digests.length && <Hash value={digests[index]} copy={copy} />}
        </Fragment>
      ))}
    </>
  );
}
