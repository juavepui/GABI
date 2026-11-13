import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveApiKey } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';

const SOURCES: Record<string, { label: string; help: string }> = {
  fred: {
    label: 'FRED (datos de la economía)',
    help: 'Gratuita: crea una cuenta en fred.stlouisfed.org y búscala en My Account → API Keys.',
  },
  tiingo: {
    label: 'Tiingo (precios antiguos)',
    help: 'Gratuita en tiingo.com. Solo hace falta para investigar con precios de hace muchos años. (Si existe la variable de entorno TIINGO_API_KEY, se usa esa.)',
  },
  nasdaq: {
    label: 'Nasdaq Data Link (empresas compradas por otras)',
    help: 'En data.nasdaq.com → Account Settings → API Key. Solo para investigación. (Si existe NASDAQ_DATA_LINK_API_KEY, se usa esa.)',
  },
  fmp: {
    label: 'Financial Modeling Prep (empresas que ya no cotizan)',
    help: 'En su web → Dashboard → API Keys. Solo para investigación. (Si existe FMP_API_KEY, se usa esa.)',
  },
};

function KeyRow({ source, configured }: { source: string; configured: boolean }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState('');
  const save = useMutation({
    mutationFn: () => saveApiKey(source, value),
    onSuccess: (settings) => {
      setValue('');
      queryClient.setQueryData(['local-settings'], settings);
    },
  });
  const info = SOURCES[source] ?? { label: source, help: '' };
  return (
    <li className="rounded-md border p-3">
      <form
        className="space-y-2"
        aria-label={`Clave ${info.label}`}
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <p className="flex justify-between gap-2">
          <span className="font-medium">{info.label}</span>
          <span className="text-muted-foreground">{configured ? 'Configurada' : 'Sin clave'}</span>
        </p>
        <div className="flex gap-2">
          <Input
            type="password"
            autoComplete="off"
            value={value}
            placeholder={configured ? 'Sustituir clave' : 'Pegar clave'}
            aria-label={`Nueva clave ${info.label}`}
            onChange={(event) => setValue(event.target.value)}
          />
          <Button type="submit" variant="outline" disabled={!value.trim()} pending={save.isPending}>
            Guardar
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {info.help} Se guarda en un fichero de tu equipo que nunca se comparte.
        </p>
        {save.isError && <p className="text-xs text-destructive">{save.error.message}</p>}
        {save.isSuccess && (
          <p role="status" className="text-xs">
            Clave guardada.
          </p>
        )}
      </form>
    </li>
  );
}

export function KeyEditor({ keys }: { keys: Record<string, boolean> }) {
  return (
    <ul className="grid gap-3 text-sm">
      {Object.entries(keys).map(([source, configured]) => (
        <KeyRow key={source} source={source} configured={configured} />
      ))}
    </ul>
  );
}
