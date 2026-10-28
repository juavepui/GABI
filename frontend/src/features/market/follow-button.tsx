import { Star } from 'lucide-react';
import { Button } from '@/shared/ui/button';
import { useFollow, useWatchlistSymbols } from './queries';

/** «Seguir» / «Siguiendo» (#182): an explicit write to the local list. `compact` is the table version:
 *  a star toggle named «Seguir SÍMBOLO» whose pressed state says whether it is followed. */
export function FollowButton({ symbol, compact = false }: { symbol: string; compact?: boolean }) {
  const symbols = useWatchlistSymbols();
  const { follow, unfollow } = useFollow(symbol);
  const following = symbols.data?.symbols.includes(symbol) ?? false;
  const action = following ? unfollow : follow;
  const busy = symbols.isPending || follow.isPending || unfollow.isPending;
  const label = following ? 'Dejar de seguir ' + symbol : 'Seguir ' + symbol;
  const error = follow.error ?? unfollow.error;
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button
        type="button"
        size={compact ? 'icon-xs' : 'sm'}
        variant={compact ? 'ghost' : following ? 'secondary' : 'outline'}
        aria-pressed={compact ? following : undefined}
        aria-label={compact ? 'Seguir ' + symbol : undefined}
        title={label}
        disabled={busy || symbols.isError}
        onClick={() => {
          follow.reset();
          unfollow.reset();
          action.mutate();
        }}
      >
        <Star
          aria-hidden="true"
          className={following ? 'fill-amber-400 text-amber-500' : 'text-muted-foreground'}
        />
        {!compact && (following ? 'Siguiendo' : 'Seguir')}
      </Button>
      {error && (
        <span role="alert" className="text-xs text-destructive">
          {error.message}
        </span>
      )}
    </span>
  );
}
