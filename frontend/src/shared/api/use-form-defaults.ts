import { useQuery } from '@tanstack/react-query';
import { getFormDefaults } from './client';

/** Form defaults decided by the backend (#190); constant while the app runs. */
export function useFormDefaults() {
  return useQuery({
    queryKey: ['form-defaults'],
    queryFn: ({ signal }) => getFormDefaults(signal),
    staleTime: Infinity,
  });
}
