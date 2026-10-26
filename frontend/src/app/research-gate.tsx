import type { ReactNode } from 'react';
import { useModel } from '@/shared/api/use-model';
import { LoadingState } from '@/shared/ui/resource-state';
import { PageHeader } from '@/shared/ui/page-header';
import { ResearchModeLink } from '@/shared/ui/research-mode';

/** Investigación only in Research mode. Reached by URL in Investor mode, it explains why and how
 *  to switch; if the mode cannot be read, the page shows and its endpoints still block on their own. */
export function ResearchGate({ children }: { children: ReactNode }) {
  const model = useModel();
  if (model.isPending) return <LoadingState />;
  if (model.data && model.data.mode !== 'RESEARCH')
    return (
      <div className="space-y-6">
        <PageHeader
          title="Investigación está en el modo Research"
          description={
            <>
              Ensayos, backtests y laboratorios son herramientas de investigación. En modo Investor
              GABI muestra solo lo necesario para decidir: Mercado, Cartera y Administración.
            </>
          }
        />
        <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4 text-sm text-muted-foreground">
          <p className="min-w-0 flex-1">
            El modo se cambia en Administración y lo aplica el servidor: en modo Investor los
            trabajos de investigación siguen bloqueados.
          </p>
          <ResearchModeLink />
        </div>
      </div>
    );
  return <>{children}</>;
}
