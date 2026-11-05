import { Link } from 'react-router-dom';
import type { HomeSummary, SummarySentence } from '@/shared/api/generated/types.gen';
import { formatNumber } from '@/shared/lib/format';
import { HowToRead } from '@/shared/ui/how-to-read';

const TONE: Record<SummarySentence['tone'], { dot: string; label: string }> = {
  good: { dot: 'bg-emerald-500', label: 'Buena noticia' },
  bad: { dot: 'bg-rose-500', label: 'Ojo' },
  neutral: { dot: 'bg-muted-foreground/50', label: 'Información' },
};

const ACTION: Partial<Record<SummarySentence['kind'], string>> = {
  moves: 'Ver empresas seguidas',
  other_model: 'Ver empresas seguidas',
  target: 'Ver la cartera propuesta',
  earnings: 'Ver eventos',
};

/** «Tu resumen de hoy» (#307): the backend writes every sentence from fixed templates; React only lays them out. */
export function HomeSummaryCard({
  summary,
  rankingReady,
}: {
  summary: HomeSummary | null | undefined;
  rankingReady: boolean;
}) {
  return (
    <section aria-label="Tu resumen de hoy" className="rounded-xl border bg-card p-5">
      <h2 className="text-lg font-semibold">Tu resumen de hoy</h2>
      {!summary ? (
        <p className="mt-2 text-sm text-muted-foreground">
          {rankingReady
            ? 'No hay resumen: faltan los datos del ranking.'
            : 'El resumen aparecerá en cuanto termine el cálculo del ranking.'}
        </p>
      ) : summary.status === 'no_companies' ? (
        <div className="mt-2 space-y-3 text-sm">
          <p className="text-muted-foreground">
            Todavía no sigues ninguna empresa ni tienes compras apuntadas en Mi cartera. Pulsa
            «Seguir» en la ficha de una empresa y aquí verás, cada día, qué ha cambiado en ella.
          </p>
          <Link className="font-medium text-primary underline" to="/descubrir">
            Abrir el Ranking
          </Link>
        </div>
      ) : (
        <ul className="mt-3 space-y-2 text-sm">
          {summary.sentences.map((sentence) => {
            const tone = TONE[sentence.tone];
            const action = ACTION[sentence.kind];
            return (
              <li key={sentence.kind} className="flex items-start gap-2.5">
                <span
                  aria-hidden="true"
                  className={'mt-1.5 size-2 shrink-0 rounded-full ' + tone.dot}
                />
                <p className="min-w-0">
                  <span className="sr-only">{tone.label}: </span>
                  {sentence.text}
                  {action && sentence.link && (
                    <>
                      {' '}
                      <Link className="font-medium text-primary underline" to={sentence.link}>
                        {action}
                      </Link>
                    </>
                  )}
                </p>
              </li>
            );
          })}
        </ul>
      )}
      {summary && (
        <HowToRead className="mt-4">
          «Tus empresas» son las que sigues y las que tienes apuntadas en Mi cartera. GABI no guarda
          la puntuación de cada día, así que compara con el día en que empezaste a seguir cada
          empresa, y solo cuenta como cambio grande moverse{' '}
          {formatNumber(summary.score_points, { digits: 0 })} puntos o {summary.rank_places} puestos
          en el ranking; lo demás es el vaivén normal de los precios. Si GABI cambió de modelo
          después, no compara, porque las puntuaciones de dos modelos no se miden igual. Los
          resultados son los de los próximos {summary.window_days} días. Las frases se escriben con
          plantillas fijas, sin inteligencia artificial: cada número sale de los datos guardados en
          tu equipo. Es información, no una recomendación de comprar o vender.
        </HowToRead>
      )}
    </section>
  );
}
