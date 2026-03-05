import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { NodeType } from '@/types/ontology';
import { useSortableData } from '@/hooks/use-sortable-data';
import SortableTableHead from './SortableTableHead';

interface NodeTypeTableProps {
  nodes: NodeType[];
  locked: boolean;
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onAdd: () => void;
}

type NodeSortKey = 'name' | 'source_table' | 'properties';

const comparators: Record<NodeSortKey, (a: NodeType, b: NodeType) => number> = {
  name: (a, b) => a.name.localeCompare(b.name),
  source_table: (a, b) => a.source_table.localeCompare(b.source_table),
  properties: (a, b) => a.properties.length - b.properties.length,
};

export default function NodeTypeTable({
  nodes,
  locked,
  onEdit,
  onDelete,
  onAdd,
}: NodeTypeTableProps) {
  const stableComparators = useMemo(() => comparators, []);
  const { sortedData, sortConfig, requestSort } = useSortableData<NodeType, NodeSortKey>(
    nodes,
    stableComparators,
  );

  const isActive = (key: NodeSortKey) => sortConfig?.key === key;
  const direction = (key: NodeSortKey) => (isActive(key) ? sortConfig!.direction : null);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          노드 타입 ({nodes.length})
        </h3>
        <Button size="sm" variant="outline" onClick={onAdd} disabled={locked}>
          + 노드 추가
        </Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead active={isActive('name')} direction={direction('name')} onSort={() => requestSort('name')}>
                이름
              </SortableTableHead>
              <SortableTableHead active={isActive('source_table')} direction={direction('source_table')} onSort={() => requestSort('source_table')}>
                원본 테이블
              </SortableTableHead>
              <SortableTableHead active={isActive('properties')} direction={direction('properties')} onSort={() => requestSort('properties')} className="text-center">
                속성 (Properties)
              </SortableTableHead>
              <TableHead className="text-right">작업</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {nodes.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  정의된 노드 타입이 없습니다
                </TableCell>
              </TableRow>
            )}
            {sortedData.map(({ item: node, originalIndex }) => (
              <TableRow key={node.name}>
                <TableCell className="font-medium">{node.name}</TableCell>
                <TableCell className="text-muted-foreground">{node.source_table}</TableCell>
                <TableCell className="text-center">{node.properties.length}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
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
