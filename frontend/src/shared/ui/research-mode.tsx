import { Link } from 'react-router-dom';
import { FlaskConical } from 'lucide-react';
import { Button } from './button';

/** Where the Investor/Research mode is changed (the backend decides it; this only links there). */
export const MODE_SETTING = '/administracion#modo';

export function ResearchModeLink() {
  return (
    <Button asChild size="sm" variant="outline">
      <Link to={MODE_SETTING}>
        <FlaskConical aria-hidden="true" />
        Activar el modo Research
      </Link>
    </Button>
  );
}

/** «This needs Research mode», with a button straight to the mode selector. */
export function ResearchModeNotice({
  action,
  className = '',
}: {
  action: string;
  className?: string;
}) {
  return (
    <div
      className={
        'flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4 text-sm text-muted-foreground ' +
        className
      }
    >
      <p className="min-w-0 flex-1">
        {action} requiere el modo Research. En modo Investor el servidor lo bloquea.
      </p>
      <ResearchModeLink />
    </div>
  );
}
