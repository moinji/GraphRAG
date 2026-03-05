import { useMemo, useState } from 'react';

export interface SortConfig<K extends string> {
  key: K;
  direction: 'asc' | 'desc';
}

export interface SortedItem<T> {
  item: T;
  originalIndex: number;
}

export function useSortableData<T, K extends string>(
  data: T[],
  comparators: Record<K, (a: T, b: T) => number>,
): {
  sortedData: SortedItem<T>[];
  sortConfig: SortConfig<K> | null;
  requestSort: (key: K) => void;
} {
  const [sortConfig, setSortConfig] = useState<SortConfig<K> | null>(null);

  const requestSort = (key: K) => {
    setSortConfig((prev) => {
      if (!prev || prev.key !== key) return { key, direction: 'asc' };
      if (prev.direction === 'asc') return { key, direction: 'desc' };
      return null; // desc → none
    });
  };

  const sortedData = useMemo(() => {
    const indexed = data.map((item, originalIndex) => ({ item, originalIndex }));
    if (!sortConfig) return indexed;

    const cmp = comparators[sortConfig.key];
    const dir = sortConfig.direction === 'asc' ? 1 : -1;
    return [...indexed].sort((a, b) => dir * cmp(a.item, b.item));
  }, [data, sortConfig, comparators]);

  return { sortedData, sortConfig, requestSort };
}
