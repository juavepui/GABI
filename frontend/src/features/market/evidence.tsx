import { Info, Clock3 } from 'lucide-react';
import type { ModelResponse, DataResponse } from '@/shared/api/generated/types.gen';
import { Badge } from '@/shared/ui/badge';
import { dateLabel } from '@/shared/lib/format';

export function Evidence({ model, data }: { model: ModelResponse; data: DataResponse }) {
  const status = {
    FROZEN: 'Hipótesis congelada',
    EXPERIMENTAL: 'Modelo experimental',
    LIVE_FORWARD: 'Seguimiento en curso',
  }[model.status];
  return (
    <div className="mb-6 space-y-3">
      <section
        aria-label="Estado de la evidencia"
        className="flex gap-3 rounded-xl border bg-secondary/60 p-4"
      >
        <Info size={18} className="mt-1 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">Ventaja frente a SPY no demostrada</p>
            <Badge variant="outline">{status}</Badge>
            <Badge variant="outline">{model.mode === 'INVESTOR' ? 'Investor' : 'Research'}</Badge>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {model.evidence_note} El score ordena empresas según el modelo; no es una rentabilidad
            esperada.
          </p>
        </div>
      </section>
      {data.status === 'stale' && (
        <p
          role="status"
          className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950"
        >
          <Clock3 size={18} aria-hidden="true" />
          Datos obsoletos. Último precio: {dateLabel(data.latest_price_date)}. Actualiza la caché
          desde Administración.
        </p>
      )}
      {data.warnings.length > 0 && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer py-1">
            Avisos de datos ({data.warnings.length})
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {data.warnings.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
