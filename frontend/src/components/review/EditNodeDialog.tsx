import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { NodeProperty, NodeType } from '@/types/ontology';

interface EditNodeDialogProps {
  node: NodeType | null;
  open: boolean;
  onClose: () => void;
  onSave: (node: NodeType) => void;
}

const PROP_TYPES = ['string', 'integer', 'float', 'boolean', 'datetime'];

function emptyProp(): NodeProperty {
  return { name: '', source_column: '', type: 'string', is_key: false };
}

export default function EditNodeDialog({ node, open, onClose, onSave }: EditNodeDialogProps) {
  const [name, setName] = useState(node?.name ?? '');
  const [sourceTable, setSourceTable] = useState(node?.source_table ?? '');
  const [properties, setProperties] = useState<NodeProperty[]>(
    node?.properties ? [...node.properties] : [],
  );

  function updateProp(idx: number, patch: Partial<NodeProperty>) {
    setProperties((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }

  function removeProp(idx: number) {
    setProperties((prev) => prev.filter((_, i) => i !== idx));
  }

  function handleSave() {
    if (!name.trim() || !sourceTable.trim()) return;
    onSave({
      name: name.trim(),
      source_table: sourceTable.trim(),
      properties: properties.filter((p) => p.name.trim() && p.source_column.trim()),
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{node ? 'Edit Node Type' : 'Add Node Type'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Name (PascalCase)</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Customer" />
            </div>
            <div className="space-y-2">
              <Label>Source Table</Label>
              <Input
                value={sourceTable}
                onChange={(e) => setSourceTable(e.target.value)}
                placeholder="customers"
              />
            </div>
          </div>

          {/* Properties sub-table */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Properties</Label>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setProperties((prev) => [...prev, emptyProp()])}
              >
                + Add Property
              </Button>
            </div>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Source Column</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-center">Key</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {properties.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground text-sm">
                        No properties.
                      </TableCell>
                    </TableRow>
                  )}
                  {properties.map((prop, i) => (
                    <TableRow key={i}>
                      <TableCell>
                        <Input
                          value={prop.name}
                          onChange={(e) => updateProp(i, { name: e.target.value })}
                          className="h-8"
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          value={prop.source_column}
                          onChange={(e) => updateProp(i, { source_column: e.target.value })}
                          className="h-8"
                        />
                      </TableCell>
                      <TableCell>
                        <Select
                          value={prop.type}
                          onValueChange={(v) => updateProp(i, { type: v })}
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PROP_TYPES.map((t) => (
                              <SelectItem key={t} value={t}>{t}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell className="text-center">
                        <Checkbox
                          checked={prop.is_key}
                          onCheckedChange={(c) => updateProp(i, { is_key: c === true })}
                        />
                      </TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" onClick={() => removeProp(i)}>
                          &times;
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!name.trim() || !sourceTable.trim()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
