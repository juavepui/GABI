import { AlertTriangle } from 'lucide-react';
import type { Metric, SuspectValue } from '@/shared/api/generated/types.gen';
import { metric } from '@/shared/lib/format';
import { Hint } from './hint';
import { Term } from './term';
import { TONE_STYLE } from './tone';

const ink = TONE_STYLE.caution.ink;

/** The plausible range in the figure's own unit: «entre −1.000,0 % y 100,0 %». */
function range(suspect: SuspectValue, unit: Metric['unit']) {
  const bound = (value: number) => metric({ value, unit });
  return `entre ${bound(suspect.low)} y ${bound(suspect.high)}`;
}

/**
 * A figure that looks wrong (#353): outside the plausible range of its kind. It is shown and,
 * if it counts, scored unchanged; this only says so. `label` adds the words next to the icon.
 */
export function SuspectMark({
  suspect,
  unit,
  label = false,
}: {
  suspect: SuspectValue | undefined;
  unit: Metric['unit'];
  label?: boolean;
}) {
  if (!suspect) return null;
  return (
    <Hint
      content={
        <>
          <strong>Parece un error.</strong> Está fuera de lo creíble para este dato (
          {range(suspect, unit)}).{' '}
          {suspect.scored
            ? 'Cuenta para la puntuación y GABI la usa tal cual, porque así se probó el modelo: tómala con cautela.'
            : 'No cuenta para la puntuación.'}
        </>
      }
    >
      <span className={'inline-flex items-center gap-1 text-xs font-normal ' + ink}>
        <AlertTriangle size={13} aria-hidden="true" />
        {label ? 'Parece un error' : <span className="sr-only">Parece un error</span>}
      </span>
    </Hint>
  );
}

/** One sentence when a figure that counts for the score looks wrong; nothing otherwise. */
export function SuspectNote({ suspects }: { suspects: Record<string, SuspectValue> }) {
  const scored = Object.values(suspects).filter((suspect) => suspect.scored).length;
  if (scored === 0) return null;
  return (
    <p
      className={
        'mb-6 flex items-start gap-2 rounded-lg border p-3 text-sm ' + TONE_STYLE.caution.box
      }
    >
      <AlertTriangle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
      <span>
        {scored === 1
          ? '1 cifra que cuenta para la puntuación parece un error'
          : `${scored} cifras que cuentan para la puntuación parecen errores`}{' '}
        (<Term k="suspect_value">fuera de lo creíble</Term>; las verás marcadas en{' '}
        <a href="#metricas" className="underline">
          las métricas
        </a>
        ). GABI {scored === 1 ? 'la usa' : 'las usa'} tal cual, porque así se probó el modelo: toma
        la puntuación de esta empresa con más cautela.
      </span>
    </p>
  );
}
