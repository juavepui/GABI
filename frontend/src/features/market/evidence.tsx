import { Info } from 'lucide-react';
import type { ModelResponse, DataResponse } from '@/shared/api/generated/types.gen';
import { dateLabel } from '@/shared/lib/format';
import { Badge } from '@/shared/ui/badge';
import { DataStatus } from './data-status';

function EvidenceNotice({ model }: { model: ModelResponse }) {
  const status = {
    FROZEN: 'Regla fija',
    EXPERIMENTAL: 'Versión de prueba',
    LIVE_FORWARD: 'En observación con datos nuevos',
  }[model.status];
  return (
    <section
      aria-label="Estado de la evidencia"
      className="flex gap-3 rounded-xl border bg-secondary/60 p-4"
    >
      <Info size={18} className="mt-1 shrink-0 text-primary" aria-hidden="true" />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold">Aún no está demostrado que GABI gane al mercado</p>
          <Badge variant="outline">{status}</Badge>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {model.evidence_note} La puntuación sirve para ordenar empresas; no dice cuánto vas a
          ganar.
          <br />
          «Regla fija» quiere decir que GABI no ajusta sus criterios a posteriori para que los
          resultados pasados parezcan mejores.
        </p>
      </div>
    </section>
  );
}

/**
 * Evidence and data state. Usual situations fold into one chip that opens the same detail;
 * an anomaly decided by the backend (data needing attention) or Research weights that are
 * not the frozen ones keep their full notice in view (#187).
 */
export function Evidence({ model, data }: { model: ModelResponse; data: DataResponse }) {
  const evidenceOpen = model.mode === 'RESEARCH' && !model.matches_frozen;
  const dataOpen = data.needs_attention === true;
  const chip = [
    !evidenceOpen && 'Aún sin pruebas de que gane al mercado',
    !dataOpen && 'Datos al día: ' + dateLabel(data.latest_price_date),
  ].filter(Boolean);
  return (
    <div className="mb-6 space-y-3">
      {evidenceOpen && <EvidenceNotice model={model} />}
      {dataOpen && <DataStatus data={data} />}
      {chip.length > 0 && (
        <details className="group">
          <summary className="inline-flex cursor-pointer items-center gap-2 rounded-full border bg-secondary/60 px-3 py-1 text-xs font-medium">
            <Info size={14} className="shrink-0 text-primary" aria-hidden="true" />
            {chip.join(' · ')}
            <span className="text-muted-foreground group-open:hidden">· Ver más</span>
          </summary>
          <div className="mt-3 space-y-3">
            {!evidenceOpen && <EvidenceNotice model={model} />}
            {!dataOpen && <DataStatus data={data} />}
          </div>
        </details>
      )}
    </div>
  );
}
