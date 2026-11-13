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
