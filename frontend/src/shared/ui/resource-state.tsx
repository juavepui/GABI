import { Link } from 'react-router-dom';
import { AlertCircle, Database, RotateCw } from 'lucide-react';
import { Button } from './button';
import { Skeleton } from './skeleton';
import { ResearchModeLink } from './research-mode';
import { ApiError } from '@/shared/api/client';

export function LoadingState() {
  return (
    <section
      aria-busy="true"
      aria-label="Cargando datos"
      className="space-y-4 rounded-xl border bg-card p-6"
    >
      <p role="status" className="text-sm text-muted-foreground">
        Consultando la caché local…
      </p>
      {[1, 2, 3, 4].map((i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </section>
  );
}
export function ErrorState({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <section role="alert" className="rounded-xl border border-destructive/30 bg-card p-7">
      <AlertCircle className="mb-3 text-destructive" aria-hidden="true" />
      <h2 className="text-lg font-semibold">No se pueden cargar los datos</h2>
      <p className="my-3 max-w-2xl text-sm text-muted-foreground">
        {error instanceof TypeError
          ? 'Comprueba que la API local esté en marcha y vuelve a intentarlo.'
          : error.message}
      </p>
      <div className="flex flex-wrap gap-2">
        {error instanceof ApiError && error.code === 'research_required' && <ResearchModeLink />}
        <Button variant="outline" onClick={retry}>
          <RotateCw aria-hidden="true" />
          Reintentar
        </Button>
      </div>
    </section>
  );
}
export function EmptyState({ filtered = false }: { filtered?: boolean }) {
  return (
    <div role="status" className="flex flex-col items-center gap-3 p-12 text-center">
      <Database className="text-muted-foreground" aria-hidden="true" />
      <h2 className="font-semibold">
        {filtered ? 'No hay empresas con estos filtros' : 'La caché local no contiene empresas'}
      </h2>
      <p className="max-w-md text-sm text-muted-foreground">
        {filtered
          ? 'Prueba con otra búsqueda o elimina algún filtro.'
          : 'Carga el universo y actualiza los datos desde Administración para empezar.'}
      </p>
      {!filtered && (
        <Button asChild variant="outline">
          <Link to="/administracion">Ir a Administración</Link>
        </Button>
      )}
    </div>
  );
}
