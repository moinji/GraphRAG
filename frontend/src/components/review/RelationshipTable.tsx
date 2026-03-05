import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { RelationshipType } from '@/types/ontology';
import { useSortableData } from '@/hooks/use-sortable-data';
import SortableTableHead from './SortableTableHead';

interface RelationshipTableProps {
  relationships: RelationshipType[];
  locked: boolean;
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onReverse: (index: number) => void;
  onAdd: () => void;
}

type RelSortKey = 'name' | 'direction' | 'derivation' | 'data_table';

const comparators: Record<RelSortKey, (a: RelationshipType, b: RelationshipType) => number> = {
  name: (a, b) => a.name.localeCompare(b.name),
  direction: (a, b) => a.source_node.localeCompare(b.source_node),
  derivation: (a, b) => a.derivation.localeCompare(b.derivation),
  data_table: (a, b) => a.data_table.localeCompare(b.data_table),
};

function derivationVariant(derivation: string) {
  if (derivation === 'llm_suggested') return 'secondary' as const;
  return 'default' as const;
}

function derivationClass(derivation: string) {
  if (derivation === 'llm_suggested') {
    return 'bg-orange-100 text-orange-800 hover:bg-orange-100';
  }
  return 'bg-blue-100 text-blue-800 hover:bg-blue-100';
}

export default function RelationshipTable({
  relationships,
  locked,
  onEdit,
  onDelete,
  onReverse,
  onAdd,
}: RelationshipTableProps) {
  const stableComparators = useMemo(() => comparators, []);
  const { sortedData, sortConfig, requestSort } = useSortableData<RelationshipType, RelSortKey>(
    relationships,
    stableComparators,
  );

  const isActive = (key: RelSortKey) => sortConfig?.key === key;
  const direction = (key: RelSortKey) => (isActive(key) ? sortConfig!.direction : null);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          관계 ({relationships.length})
        </h3>
        <Button size="sm" variant="outline" onClick={onAdd} disabled={locked}>
          + 관계 추가
        </Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead active={isActive('name')} direction={direction('name')} onSort={() => requestSort('name')}>
                이름
              </SortableTableHead>
              <SortableTableHead active={isActive('direction')} direction={direction('direction')} onSort={() => requestSort('direction')}>
                방향
              </SortableTableHead>
              <SortableTableHead active={isActive('derivation')} direction={direction('derivation')} onSort={() => requestSort('derivation')}>
                도출 방식
              </SortableTableHead>
              <SortableTableHead active={isActive('data_table')} direction={direction('data_table')} onSort={() => requestSort('data_table')}>
                데이터 테이블
              </SortableTableHead>
              <TableHead className="text-right">작업</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {relationships.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  정의된 관계가 없습니다
                </TableCell>
              </TableRow>
            )}
            {sortedData.map(({ item: rel, originalIndex }) => (
              <TableRow key={`${rel.name}-${originalIndex}`}>
                <TableCell className="font-medium">{rel.name}</TableCell>
                <TableCell>
                  <span className="text-sm">
                    {rel.source_node} &rarr; {rel.target_node}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge
                    variant={derivationVariant(rel.derivation)}
                    className={derivationClass(rel.derivation)}
                  >
                    {rel.derivation}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">{rel.data_table}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onReverse(originalIndex)}
                      disabled={locked}
                      title="방향 반전"
                    >
                      &#8646;
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onEdit(originalIndex)}
                      disabled={locked}
                    >
                      수정
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive"
                      onClick={() => onDelete(originalIndex)}
                      disabled={locked}
                    >
                      삭제
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
