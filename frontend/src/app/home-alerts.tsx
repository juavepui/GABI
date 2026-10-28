import { Link } from 'react-router-dom';
import type { HomeAlert } from '@/shared/api/generated/types.gen';
import { jobName } from '@/shared/lib/jobs';

const SEVERITY: Record<HomeAlert['severity'], { label: string; tone: string }> = {
  high: {
    label: 'Importante',
    tone: 'border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950',
  },
  medium: {
    label: 'Revisar',
    tone: 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950',
  },
  info: { label: 'Aviso', tone: 'border-border bg-muted/40' },
};

const day = (value: string | null | undefined) =>
  value
    ? new Date(value + 'T12:00:00').toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
    : '';

function list(symbols: string[], limit = 5) {
  const shown = symbols.slice(0, limit).join(', ');
  return symbols.length > limit ? `${shown} y ${symbols.length - limit} más` : shown;
}

/** The sentence of each alert kind; the backend decides which alerts exist and their order. */
function sentence(alert: HomeAlert): { text: string; action: string } {
  const detail = (alert.detail ?? {}) as Record<string, unknown>;
  const count = alert.symbols.length;
  switch (alert.kind) {
    case 'earnings': {
      const holdings = detail.scope === 'holdings';
      const who = holdings
        ? count === 1
          ? 'Una empresa de Mi cartera presenta'
          : `${count} empresas de Mi cartera presentan`
        : count === 1
          ? 'Una de tus candidatas presenta'
          : `${count} de tus candidatas presentan`;
      return {
        text: `${who} resultados esta semana: ${list(alert.symbols)} (desde el ${day(alert.date)}).`,
        action: holdings ? 'Ver Mi cartera' : 'Ver eventos',
      };
    }
    case 'ex_dividend':
    case 'dividend_payment':
      return {
        text: `${alert.kind === 'ex_dividend' ? 'Fecha ex-dividendo' : 'Pago de dividendo'} el ${day(alert.date)}: ${list(alert.symbols)}.`,
        action: 'Ver la ficha de ' + alert.symbols[0],
      };
    case 'top_changes': {
      const entered = (detail.entered as string[] | undefined) ?? [];
      const exited = (detail.exited as string[] | undefined) ?? [];
      const parts = [
        entered.length > 0 &&
          `${list(entered)} ${entered.length === 1 ? 'ha entrado' : 'han entrado'} en el Top-20`,
        exited.length > 0 && `${list(exited)} ${exited.length === 1 ? 'ha salido' : 'han salido'}`,
      ].filter(Boolean);
      return {
        text: `${parts.join('; ')} respecto a «${String(detail.snapshot ?? 'la última foto')}» (${day(alert.date)}).`,
        action: 'Ver eventos',
      };
    }
    case 'filings':
      return {
        text: `Cambios materiales en los últimos informes SEC de ${list(alert.symbols)}.`,
        action: 'Ver eventos',
      };
    case 'job_failed': {
      const failures = Number(detail.failures ?? 0);
      return {
        text:
          `«${jobName(String(detail.job_kind))}» falló el ${day(alert.date)}` +
          (detail.failure ? `: ${String(detail.failure).toLowerCase()}` : '') +
          (failures > 0 ? `, con ${failures} fallos de fuente` : '') +
          '.',
        action: 'Ver Administración',
      };
    }
    case 'thesis_review':
      return {
        text: `Tu tesis de ${alert.symbols[0]} tenía revisión el ${day(alert.date)}.`,
        action: 'Abrir el diario',
      };
  }
}

/** «Qué requiere tu atención»: alerts already ordered by severity and date. */
export function HomeAlerts({ alerts }: { alerts: HomeAlert[] }) {
  return (
    <section aria-label="Qué requiere tu atención" className="rounded-xl border bg-card p-5">
      <h2 className="text-lg font-semibold">Qué requiere tu atención</h2>
      {alerts.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">
          Nada pendiente: sin resultados ni dividendos esta semana, sin cambios en el Top-20, sin
          trabajos fallidos ni tesis por revisar.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {alerts.map((alert, index) => {
            const { text, action } = sentence(alert);
            const severity = SEVERITY[alert.severity];
            return (
              <li
                key={alert.kind + index}
                className={'rounded-lg border p-3 text-sm ' + severity.tone}
              >
                <span className="mr-2 text-xs font-semibold uppercase tracking-wide">
                  {severity.label}
                </span>
                {text}{' '}
                <Link className="font-medium text-primary underline" to={alert.link}>
                  {action}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
