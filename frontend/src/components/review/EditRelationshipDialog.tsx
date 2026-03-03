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
import type { RelProperty, RelationshipType } from '@/types/ontology';

interface EditRelationshipDialogProps {
  relationship: RelationshipType | null;
  nodeNames: string[];
  open: boolean;
  onClose: () => void;
  onSave: (rel: RelationshipType) => void;
}

const DERIVATIONS = ['fk_direct', 'fk_join_table', 'llm_suggested'];
const PROP_TYPES = ['string', 'integer', 'float', 'boolean', 'datetime'];

function emptyProp(): RelProperty {
  return { name: '', source_column: '', type: 'string' };
}

export default function EditRelationshipDialog({
  relationship,
  nodeNames,
  open,
  onClose,
  onSave,
}: EditRelationshipDialogProps) {
  const [name, setName] = useState(relationship?.name ?? '');
  const [sourceNode, setSourceNode] = useState(relationship?.source_node ?? '');
  const [targetNode, setTargetNode] = useState(relationship?.target_node ?? '');
  const [dataTable, setDataTable] = useState(relationship?.data_table ?? '');
  const [sourceKeyColumn, setSourceKeyColumn] = useState(relationship?.source_key_column ?? '');
  const [targetKeyColumn, setTargetKeyColumn] = useState(relationship?.target_key_column ?? '');
  const [derivation, setDerivation] = useState(relationship?.derivation ?? 'fk_direct');
  const [properties, setProperties] = useState<RelProperty[]>(
    relationship?.properties ? [...relationship.properties] : [],
  );

  function updateProp(idx: number, patch: Partial<RelProperty>) {
    setProperties((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }

  function removeProp(idx: number) {
    setProperties((prev) => prev.filter((_, i) => i !== idx));
  }

  function handleSave() {
    if (!name.trim() || !sourceNode || !targetNode || !dataTable.trim()) return;
    onSave({
      name: name.trim(),
      source_node: sourceNode,
      target_node: targetNode,
      data_table: dataTable.trim(),
      source_key_column: sourceKeyColumn.trim(),
      target_key_column: targetKeyColumn.trim(),
      properties: properties.filter((p) => p.name.trim() && p.source_column.trim()),
      derivation,
    });
  }

  const valid = name.trim() && sourceNode && targetNode && dataTable.trim();

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {relationship ? 'Edit Relationship' : 'Add Relationship'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Name (UPPER_SNAKE)</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="PLACED" />
            </div>
            <div className="space-y-2">
              <Label>Data Table</Label>
              <Input
                value={dataTable}
                onChange={(e) => setDataTable(e.target.value)}
                placeholder="orders"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Source Node</Label>
              <Select value={sourceNode} onValueChange={setSourceNode}>
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {nodeNames.map((n) => (
                    <SelectItem key={n} value={n}>{n}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Target Node</Label>
              <Select value={targetNode} onValueChange={setTargetNode}>
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {nodeNames.map((n) => (
                    <SelectItem key={n} value={n}>{n}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>Source Key Column</Label>
              <Input
                value={sourceKeyColumn}
                onChange={(e) => setSourceKeyColumn(e.target.value)}
                placeholder="customer_id"
              />
            </div>
            <div className="space-y-2">
              <Label>Target Key Column</Label>
              <Input
                value={targetKeyColumn}
                onChange={(e) => setTargetKeyColumn(e.target.value)}
                placeholder="id"
              />
            </div>
            <div className="space-y-2">
              <Label>Derivation</Label>
              <Select value={derivation} onValueChange={setDerivation}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DERIVATIONS.map((d) => (
                    <SelectItem key={d} value={d}>{d}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {properties.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-muted-foreground text-sm">
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
          <Button onClick={handleSave} disabled={!valid}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
