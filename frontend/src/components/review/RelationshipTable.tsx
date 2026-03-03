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

interface RelationshipTableProps {
  relationships: RelationshipType[];
  locked: boolean;
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onReverse: (index: number) => void;
  onAdd: () => void;
}

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
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          Relationships ({relationships.length})
        </h3>
        <Button size="sm" variant="outline" onClick={onAdd} disabled={locked}>
          + Add Relationship
        </Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Direction</TableHead>
              <TableHead>Derivation</TableHead>
              <TableHead>Data Table</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {relationships.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No relationships defined.
                </TableCell>
              </TableRow>
            )}
            {relationships.map((rel, i) => (
              <TableRow key={`${rel.name}-${i}`}>
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
                      onClick={() => onReverse(i)}
                      disabled={locked}
                      title="Reverse direction"
                    >
                      &#8646;
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onEdit(i)}
                      disabled={locked}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive"
                      onClick={() => onDelete(i)}
                      disabled={locked}
                    >
                      Delete
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
