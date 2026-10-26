import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { PageHeader } from '@/shared/ui/page-header';
import { SnapshotProgress } from './snapshot-progress';
import { SnapshotPicker } from './snapshot-picker';
import { useSnapshots } from './queries';

/** Seguimiento (#193): how each saved basket has done against SPY since it was saved. Saving a
 *  basket is an action of Cartera objetivo; its events and filings live in Eventos. */
export function TrackingPage() {
  const snapshots = useSnapshots();
  const [selected, setSelected] = useState<number | null>(null);
  const items = snapshots.data?.items ?? [];
  const active = selected ?? items[0]?.id ?? null;
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/cartera', label: 'Cartera' }}
        title="Seguimiento de cestas"
        description={
          <>
            Cómo han evolucionado frente a SPY las carteras que guardaste, con sus mismas empresas y
            el mismo peso. Es seguimiento, nunca una orden de compra o venta.
          </>
        }
      />
      {snapshots.isPending && <LoadingState />}
      {snapshots.isError && (
        <ErrorState error={snapshots.error} retry={() => void snapshots.refetch()} />
      )}
      {snapshots.isSuccess && items.length === 0 && (
        <p className="rounded-xl border bg-card p-5 text-sm">
          Aún no sigues ninguna cesta. En{' '}
          <Link className="text-primary underline" to="/cartera">
            Cartera objetivo
          </Link>
          , «Guardar esta cartera para seguirla» guarda la de hoy.
        </p>
      )}
      {active != null && (
        <>
          <div className="max-w-md">
            <SnapshotPicker
              label="Cesta guardada"
              items={items}
              value={active}
              onChange={setSelected}
            />
          </div>
          <SnapshotProgress id={active} />
          <p className="text-sm text-muted-foreground">
            Los cambios del ranking y de los filings de esta cesta están en{' '}
            <Link className="text-primary underline" to="/eventos">
              Eventos
            </Link>
            .
          </p>
        </>
      )}
    </div>
  );
}
