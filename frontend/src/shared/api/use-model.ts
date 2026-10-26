import { useQuery } from '@tanstack/react-query';
import { getModel } from './client';

/** The model and its Investor/Research mode, as the backend decides it. Changing the mode
 *  invalidates every query, so this refreshes everywhere at once. */
export function useModel() {
  return useQuery({ queryKey: ['model'], queryFn: ({ signal }) => getModel(signal) });
}

/** Research tools are shown only once the backend confirms Research mode. */
export function useResearchMode(): boolean {
  return useModel().data?.mode === 'RESEARCH';
}
