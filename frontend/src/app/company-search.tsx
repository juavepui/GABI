import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getRanking, type RankingQuery } from '@/shared/api/client';
import { CompanyPicker } from '@/shared/ui/company-picker';

// The same query as the company pickers of Comparar, so both share one cached list.
const UNIVERSE: RankingQuery = { limit: 500, hide_no_data: false };

/** «Go to a company» from any page. The list is read the first time the box takes focus,
 *  not on every page load. */
export function CompanySearch() {
  const navigate = useNavigate();
  const [wanted, setWanted] = useState(false);
  const universe = useQuery({
    queryKey: ['market', 'ranking', UNIVERSE],
    queryFn: ({ signal }) => getRanking(UNIVERSE, signal),
    enabled: wanted,
  });
  return (
    <div
      className="min-w-0 flex-1 md:w-72 md:flex-none"
      onFocusCapture={() => setWanted(true)}
      role="search"
    >
      <CompanyPicker
        label="Buscar empresa"
        hideLabel
        options={universe.data?.items ?? []}
        value=""
        onChange={(symbol) => symbol && navigate('/empresas/' + encodeURIComponent(symbol))}
      />
    </div>
  );
}
