import { useQuery } from '@tanstack/react-query';
import { getRanking, getCompany, type RankingQuery } from '@/shared/api/client';

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
