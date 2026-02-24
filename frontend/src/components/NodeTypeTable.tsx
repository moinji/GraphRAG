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

interface NodeTypeTableProps {
  nodes: NodeType[];
  locked: boolean;
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onAdd: () => void;
}

export default function NodeTypeTable({
  nodes,
  locked,
  onEdit,
  onDelete,
  onAdd,
}: NodeTypeTableProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          Node Types ({nodes.length})
        </h3>
        <Button size="sm" variant="outline" onClick={onAdd} disabled={locked}>
          + Add Node
        </Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Source Table</TableHead>
              <TableHead className="text-center">Properties</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {nodes.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No node types defined.
                </TableCell>
              </TableRow>
            )}
            {nodes.map((node, i) => (
              <TableRow key={node.name}>
                <TableCell className="font-medium">{node.name}</TableCell>
                <TableCell className="text-muted-foreground">{node.source_table}</TableCell>
                <TableCell className="text-center">{node.properties.length}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
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
