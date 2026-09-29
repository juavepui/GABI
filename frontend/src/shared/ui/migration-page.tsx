import { ArrowUpRight } from 'lucide-react';
import { Button } from './button';

export function MigrationPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="max-w-2xl">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Migración por fases
      </p>
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{description}</p>
      <div className="mt-6 rounded-xl border bg-card p-6">
        <h2 className="font-semibold">Disponible en Streamlit</h2>
        <p className="mb-5 mt-2 text-sm text-muted-foreground">
          Abre la interfaz local de Streamlit para continuar con este flujo. El frontend React
          incorpora primero el Screener y la ficha de empresa.
        </p>
        <Button asChild>
          <a href="http://localhost:8501" target="_blank" rel="noreferrer">
            Abrir Streamlit <ArrowUpRight aria-hidden="true" />
          </a>
        </Button>
      </div>
    </div>
  );
}
