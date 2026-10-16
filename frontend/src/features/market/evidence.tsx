import { Info } from 'lucide-react';
import type { ModelResponse, DataResponse } from '@/shared/api/generated/types.gen';
import { Badge } from '@/shared/ui/badge';
import { DataStatus } from './data-status';

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
      <DataStatus data={data} />
    </div>
  );
}
