import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  followCompany,
  getCompany,
  getRanking,
  getSnapshots,
  getWatchlistSymbols,
  unfollowCompany,
  type RankingQuery,
} from '@/shared/api/client';

export function useRanking(query: RankingQuery) {
  return useQuery({
    queryKey: ['market', 'ranking', query],
    queryFn: ({ signal }) => getRanking(query, signal),
  });
}
export function useCompany(symbol: string, bars: number) {
  return useQuery({
    queryKey: ['market', 'company', symbol, bars],
    queryFn: ({ signal }) => getCompany(symbol, bars, signal),
  });
}
/** The saved baskets (ranking snapshots), newest first. */
export function useSnapshots() {
  return useQuery({
    queryKey: ['market', 'snapshots'],
    queryFn: ({ signal }) => getSnapshots(signal),
  });
}

/** The followed symbols alone: what every «Seguir» button needs, without reading the ranking. */
export function useWatchlistSymbols() {
  return useQuery({
    queryKey: ['market', 'watchlist', 'symbols'],
    queryFn: ({ signal }) => getWatchlistSymbols(signal),
  });
}
/** Follow or stop following a company; both refresh every view of the list. */
export function useFollow(symbol: string) {
  const client = useQueryClient();
  const changed = () => client.invalidateQueries({ queryKey: ['market', 'watchlist'] });
  return {
    follow: useMutation({ mutationFn: () => followCompany(symbol), onSuccess: changed }),
    unfollow: useMutation({ mutationFn: () => unfollowCompany(symbol), onSuccess: changed }),
  };
}
