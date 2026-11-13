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
        title="Carteras guardadas"
        description={
          <>
            Cómo les ha ido a las carteras que guardaste, con las mismas empresas y el mismo
            reparto, frente al S&amp;P 500 (SPY). Es solo seguimiento: nunca compra ni vende.
          </>
        }
      />
      {snapshots.isPending && <LoadingState />}
      {snapshots.isError && (
        <ErrorState error={snapshots.error} retry={() => void snapshots.refetch()} />
      )}
      {snapshots.isSuccess && items.length === 0 && (
        <p className="rounded-xl border bg-card p-5 text-sm">
          Aún no has guardado ninguna cartera. En{' '}
          <Link className="text-primary underline" to="/cartera">
            Cartera objetivo
          </Link>
          , pulsa «Guardar esta cartera para seguirla» para guardar la de hoy.
        </p>
      )}
      {active != null && (
        <>
          <div className="max-w-md">
            <SnapshotPicker
              label="Cartera guardada"
              items={items}
              value={active}
              onChange={setSelected}
            />
          </div>
          <SnapshotProgress id={active} />
          <p className="text-sm text-muted-foreground">
            Los cambios en el ranking y en los informes oficiales de estas empresas están en{' '}
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
