import { Link } from 'react-router-dom';
import type { ScoreBlockEvidence, ScoreBlocksEvidence } from '@/shared/api/generated/types.gen';
import { formatNumber } from '@/shared/lib/format';
import { Badge } from './badge';

export const FACTOR_LAB = '/investigacion/factores';

const NAMES: Record<ScoreBlockEvidence['block'], string> = {
  value: 'valoración',
  quality: 'calidad',
  momentum: 'momentum',
  risk: 'riesgo',
};

function list(names: string[]): string {
  return names.length < 2 ? names.join('') : names.slice(0, -1).join(', ') + ' y ' + names.at(-1);
}

/** A block's published evidence, discreet: its classification and, on hover, the mean IC and counts. */
export function BlockEvidenceBadge({ block }: { block: ScoreBlockEvidence }) {
  if (!block.classification_label)
    return (
      <Badge variant="outline" className="text-muted-foreground">
        Sin publicar
      </Badge>
    );
  const title =
    `${block.metrics_at_classification} de ${block.metrics.length} métricas con «${block.classification_label}». ` +
    `Relación media con la rentabilidad posterior (IC): ${formatNumber(block.ic_mean, { digits: 3, fixed: true })}. ` +
    `Pasan la prueba estadística exigente (Holm al 5 %): ${block.holm_significant}.`;
  return (
    <Badge
      variant="outline"
      className={block.metrics_with_evidence ? '' : 'text-muted-foreground'}
      title={title}
    >
      {block.classification_label}
      <span className="sr-only"> · {title}</span>
    </Badge>
  );
}

/** «El score combina bloques con evidencia desigual», written from the published catalogue. */
export function UnevenEvidenceNote({
  evidence,
  className = '',
}: {
  evidence: ScoreBlocksEvidence;
  className?: string;
}) {
  const groups = new Map<string, string[]>();
  for (const block of evidence.blocks) {
    const label = (block.classification_label ?? 'sin publicar').toLowerCase();
    groups.set(label, [...(groups.get(label) ?? []), NAMES[block.block]]);
  }
  const holm =
    evidence.holm_significant_count === 0
      ? 'ninguna métrica ha pasado la prueba estadística más exigente (Holm al 5 %)'
      : `${evidence.holm_significant_count} métricas pasan la prueba estadística más exigente (Holm al 5 %)`;
  return (
    <p className={'text-xs leading-relaxed text-muted-foreground ' + className}>
      Cuánto se ha comprobado cada apartado con datos del pasado: {holm};{' '}
      {[...groups].map(([label, names]) => `${label} en ${list(names)}`).join('; ')}.
      {evidence.holm_significant_count === 0 &&
        ' En pocas palabras: ningún apartado ha demostrado todavía con claridad que sirva para elegir mejores acciones.'}{' '}
      Es solo información; no cambia la puntuación.{' '}
      <Link className="text-primary underline" to={FACTOR_LAB}>
        Ver el detalle
      </Link>
    </p>
  );
}
