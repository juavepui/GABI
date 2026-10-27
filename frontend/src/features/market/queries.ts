import { useQuery } from '@tanstack/react-query';
import {
  getRanking,
  getCompany,
  getScoreBlocksEvidence,
  getSnapshots,
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
/** Published Factor Zoo evidence of each score block (#185): a sealed file, read once and kept. */
export function useBlockEvidence() {
  return useQuery({
    queryKey: ['market', 'score-blocks-evidence'],
    queryFn: ({ signal }) => getScoreBlocksEvidence(signal),
    staleTime: Infinity,
  });
}
