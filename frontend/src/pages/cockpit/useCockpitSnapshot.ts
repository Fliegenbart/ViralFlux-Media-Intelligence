import { useEffect, useState } from 'react';
import { GELO_SNAPSHOT } from './snapshot';
import type { CockpitSnapshot } from './types';

/**
 * Hook that resolves a CockpitSnapshot.
 *
 * Today: returns the curated GELO fixture.
 * Tomorrow: swap to `useSWR('/api/cockpit/snapshot', fetcher)` — shape identical.
 */
export function useCockpitSnapshot(): { snapshot: CockpitSnapshot | null; loading: boolean } {
  const [snapshot, setSnapshot] = useState<CockpitSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // tiny delay to mimic async and let transitions breathe
    const t = setTimeout(() => {
      setSnapshot(GELO_SNAPSHOT);
      setLoading(false);
    }, 60);
    return () => clearTimeout(t);
  }, []);

  return { snapshot, loading };
}
