import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveApiKey } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';

const SOURCES: Record<string, { label: string; help: string }> = {
  fred: {
    label: 'FRED (panel macro)',
    help: 'Clave gratuita en fred.stlouisfed.org → My Account → API Keys.',
  },
  tiingo: {
    label: 'Tiingo (histórico de precios)',
    help: 'Cuenta gratuita en tiingo.com; la variable TIINGO_API_KEY tiene prioridad.',
  },
  nasdaq: {
    label: 'Nasdaq Data Link (empresas absorbidas)',
    help: 'Account Settings → API Key en data.nasdaq.com; NASDAQ_DATA_LINK_API_KEY tiene prioridad.',
  },
  fmp: {
    label: 'Financial Modeling Prep (empresas desaparecidas)',
    help: 'Dashboard → API Keys; la variable FMP_API_KEY tiene prioridad.',
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
          <Button type="submit" variant="outline" disabled={!value.trim() || save.isPending}>
            Guardar
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {info.help} Se guarda en un fichero local excluido del control de versiones.
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
