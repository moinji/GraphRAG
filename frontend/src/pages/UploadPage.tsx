import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { uploadDDL, generateOntology } from '@/api/client';
import type { ERDSchema, OntologyGenerateResponse } from '@/types/ontology';

interface UploadPageProps {
  onGenerated: (result: OntologyGenerateResponse, erd: ERDSchema) => void;
}

export default function UploadPage({ onGenerated }: UploadPageProps) {
  const [file, setFile] = useState<File | null>(null);
  const [erd, setErd] = useState<ERDSchema | null>(null);
  const [includeLlm, setIncludeLlm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTable, setExpandedTable] = useState<string | null>(null);

  // FK lookup: target_table → source entries
  const fkBySource = new Map<string, { source_column: string; target_table: string; target_column: string }[]>();
  if (erd) {
    for (const fk of erd.foreign_keys) {
      const list = fkBySource.get(fk.source_table) ?? [];
      list.push({ source_column: fk.source_column, target_table: fk.target_table, target_column: fk.target_column });
      fkBySource.set(fk.source_table, list);
    }
  }

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const result = await uploadDDL(file);
      setErd(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    if (!erd) return;
    setLoading(true);
    setError(null);
    try {
      const result = await generateOntology(erd, !includeLlm);
      onGenerated(result, erd);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Upload DDL</CardTitle>
          <CardDescription>
            Upload a SQL DDL file to parse the schema and generate an ontology.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ddl-file">DDL File (.sql)</Label>
            <Input
              id="ddl-file"
              type="file"
              accept=".sql,.txt"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setErd(null);
                setExpandedTable(null);
              }}
            />
          </div>
          <Button onClick={handleUpload} disabled={!file || loading}>
            {loading && !erd ? 'Uploading...' : 'Upload'}
          </Button>
        </CardContent>
      </Card>

      {erd && (
        <>
          {/* Summary counts */}
          <Card>
            <CardHeader>
              <CardTitle>ERD Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="rounded-lg border p-3">
                  <p className="text-muted-foreground">Tables</p>
                  <p className="text-2xl font-bold">{erd.tables.length}</p>
                </div>
                <div className="rounded-lg border p-3">
                  <p className="text-muted-foreground">Foreign Keys</p>
                  <p className="text-2xl font-bold">{erd.foreign_keys.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Tables detail */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Tables</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Table Name</TableHead>
                      <TableHead className="text-center">Columns</TableHead>
                      <TableHead className="text-center">PK</TableHead>
                      <TableHead className="text-center">FKs</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {erd.tables.map((table) => {
                      const tableFks = fkBySource.get(table.name) ?? [];
                      const isExpanded = expandedTable === table.name;
                      return (
                        <TableRow
                          key={table.name}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => setExpandedTable(isExpanded ? null : table.name)}
                        >
                          <TableCell className="font-medium">{table.name}</TableCell>
                          <TableCell className="text-center">{table.columns.length}</TableCell>
                          <TableCell className="text-center">
                            <code className="text-xs">{table.primary_key ?? '-'}</code>
                          </TableCell>
                          <TableCell className="text-center">
                            {tableFks.length > 0 ? tableFks.length : '-'}
                          </TableCell>
                          <TableCell className="text-right text-muted-foreground text-xs">
                            {isExpanded ? '▲' : '▼'}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>

              {/* Expanded table detail */}
              {expandedTable && (() => {
                const table = erd.tables.find((t) => t.name === expandedTable);
                if (!table) return null;
                const tableFks = fkBySource.get(table.name) ?? [];
                const fkColumns = new Set(tableFks.map((fk) => fk.source_column));

                return (
                  <div className="mt-4 space-y-4">
                    {/* Columns */}
                    <div>
                      <h4 className="text-sm font-medium mb-2">
                        Columns — <code className="text-xs">{table.name}</code>
                      </h4>
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Column</TableHead>
                              <TableHead>Type</TableHead>
                              <TableHead className="text-center">Nullable</TableHead>
                              <TableHead className="text-center">Flags</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {table.columns.map((col) => (
                              <TableRow key={col.name}>
                                <TableCell className="font-mono text-sm">{col.name}</TableCell>
                                <TableCell className="font-mono text-sm text-muted-foreground">
                                  {col.data_type}
                                </TableCell>
                                <TableCell className="text-center text-sm">
                                  {col.nullable ? 'YES' : 'NO'}
                                </TableCell>
                                <TableCell className="text-center">
                                  <div className="flex justify-center gap-1">
                                    {col.is_primary_key && (
                                      <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">PK</Badge>
                                    )}
                                    {fkColumns.has(col.name) && (
                                      <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">FK</Badge>
                                    )}
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    {/* FKs for this table */}
                    {tableFks.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium mb-2">Foreign Keys</h4>
                        <div className="rounded-md border">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Column</TableHead>
                                <TableHead>References</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {tableFks.map((fk) => (
                                <TableRow key={fk.source_column}>
                                  <TableCell className="font-mono text-sm">{fk.source_column}</TableCell>
                                  <TableCell className="font-mono text-sm text-muted-foreground">
                                    {fk.target_table}.{fk.target_column}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </CardContent>
          </Card>

          {/* FK relationships overview */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Foreign Key Relationships</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Source</TableHead>
                      <TableHead />
                      <TableHead>Target</TableHead>
                      <TableHead>Column Mapping</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {erd.foreign_keys.map((fk, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-sm">{fk.source_table}</TableCell>
                        <TableCell className="text-center text-muted-foreground">&rarr;</TableCell>
                        <TableCell className="font-mono text-sm">{fk.target_table}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {fk.source_column} &rarr; {fk.target_column}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Generate action */}
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="include-llm"
                  checked={includeLlm}
                  onCheckedChange={(checked) => setIncludeLlm(checked === true)}
                />
                <Label htmlFor="include-llm">Include LLM enrichment</Label>
              </div>

              <Button onClick={handleGenerate} disabled={loading} size="lg">
                {loading ? 'Generating...' : 'Generate Ontology'}
              </Button>
            </CardContent>
          </Card>
        </>
      )}

      {error && (
        <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
