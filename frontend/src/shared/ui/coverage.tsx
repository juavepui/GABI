const BLOCKS: Record<string, string> = {
  Value: 'Valoración',
  Quality: 'Calidad',
  Momentum: 'Momentum (tendencia del precio)',
  Risk: 'Riesgo',
};

/**
 * The backend's coverage warnings in plain words. Their wording is pinned by the legacy equivalence
 * fixtures, so the translation lives here; an unknown text is shown as it comes.
 */
export function plainWarning(text: string): string {
  return text
    .replace(/^\*\*(Value|Quality|Momentum|Risk)\*\*/, (_, block: string) => `**${BLOCKS[block]}**`)
    .replace(
      /solo (\d+) ?% del universo tiene TODAS las métricas de este bloque \(umbral configurado: (\d+) ?%\)\./,
      'solo el $1 % de las empresas tiene todos los datos de este apartado (mínimo pedido: $2 %).',
    )
    .replace(
      /^Identidad histórica sin acreditar en (\d+) ?% del universo; excluida del score\./,
      'En el $1 % de las empresas no se ha podido confirmar su historia (fusiones, cambios de nombre); no reciben puntuación.',
    )
    .replace(
      /^Sector aproximado o ausente en (\d+) ?% del universo\./,
      'En el $1 % de las empresas el sector es aproximado o falta, así que la comparación con su sector es menos fiable.',
    );
}

/** Backend warnings mark emphasis with **…**; show it as bold without parsing other Markdown. */
export function WarningText({ text }: { text: string }) {
  return (
    <>
      {plainWarning(text)
        .split('**')
        .map((part, index) =>
          index % 2 ? <strong key={index}>{part}</strong> : <span key={index}>{part}</span>,
        )}
    </>
  );
}

export function CoverageThreshold({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-xs font-medium">
      Mínimo de empresas con todos los datos de cada apartado (%)
      <input
        className="mt-1.5 block h-10 w-28 rounded-md border bg-background px-2 text-sm"
        type="number"
        min={0}
        max={100}
        step={5}
        value={Math.round(value * 100)}
        onChange={(event) => onChange(Math.min(Math.max(Number(event.target.value), 0), 100) / 100)}
      />
    </label>
  );
}
