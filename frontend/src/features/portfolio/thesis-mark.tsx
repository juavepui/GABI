import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getThesisCounts } from '@/shared/api/client';

/** Open and total theses per company, one batched read shared by every position of a page. */
function useThesisCounts() {
  return useQuery({
    queryKey: ['portfolio', 'journal', 'symbols'],
    queryFn: ({ signal }) => getThesisCounts(signal),
  });
}

/** «Sin tesis» on a position whose company has no open thesis (#186), linking to write one. */
export function ThesisMark({ symbol }: { symbol: string }) {
  const counts = useThesisCounts();
  if (!counts.data || counts.data.items[symbol]?.open) return null;
  return (
    <Link
      className="block text-xs text-amber-700 underline dark:text-amber-300"
      to={'/empresas/' + encodeURIComponent(symbol) + '#tesis'}
    >
      {counts.data.items[symbol] ? 'Sin tesis abierta' : 'Sin tesis'} · escribir una
    </Link>
  );
}
