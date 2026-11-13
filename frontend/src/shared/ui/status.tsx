import type { ReactNode } from 'react';
import { TONE_STYLE, type Tone } from './tone';

/**
 * A state as coloured border + icon + word (#320), never colour alone, so it reads the same for people
 * who do not tell red from green and for screen readers.
 */
export function StatusTag({
  tone,
  label,
  className = '',
}: {
  tone: Tone;
  label: string;
  className?: string;
}) {
  const style = TONE_STYLE[tone];
  const Icon = style.icon;
  return (
    <span
      data-tone={tone}
      className={
        'inline-flex w-fit items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ' +
        style.box +
        ' ' +
        className
      }
    >
      <Icon size={14} aria-hidden="true" className="shrink-0" />
      {label}
    </span>
  );
}

const ARROW = { up: '↑', down: '↓', flat: '→' } as const;

/**
 * Which way something moved, in a neutral colour (#320): the arrow and the word say the direction; whether
 * the level is good or bad is said elsewhere, by its own colour. Mixing both in one colour («23» in red next to
 * «subiendo» in green) leaves the reader not knowing if it is good or bad news.
 */
export function Direction({
  value,
  children,
  words = { up: 'sube', down: 'baja', flat: 'igual' },
  className = '',
}: {
  value: number;
  children?: ReactNode;
  words?: { up: string; down: string; flat: string };
  className?: string;
}) {
  const way = value > 0 ? 'up' : value < 0 ? 'down' : 'flat';
  return (
    <span data-direction={way} className={'text-muted-foreground ' + className}>
      <span aria-hidden="true">{ARROW[way]} </span>
      {words[way]}
      {children != null && <> {children}</>}
    </span>
  );
}
