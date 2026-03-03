import { useState, useEffect, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import ModeToggle from '@/components/review/ModeToggle';
import EvalCard from '@/components/review/EvalCard';
import NodeTypeTable from '@/components/review/NodeTypeTable';
import RelationshipTable from '@/components/review/RelationshipTable';
import DiffPanel from '@/components/review/DiffPanel';
import EditNodeDialog from '@/components/review/EditNodeDialog';
import EditRelationshipDialog from '@/components/review/EditRelationshipDialog';
import { updateVersion, approveVersion, startKGBuild, getKGBuildStatus, uploadCSVFiles } from '@/api/client';
import type {
  CSVTableSummary,
  ERDSchema,
  EvalMetrics,
  KGBuildResponse,
  NodeType,
  OntologyGenerateResponse,
  OntologySpec,
  RelationshipType,
} from '@/types/ontology';

interface ReviewPageProps {
  result: OntologyGenerateResponse;
  erd: ERDSchema;
  onGoToQuery?: () => void;
}

export default function ReviewPage({ result, erd, onGoToQuery }: ReviewPageProps) {
  const [mode, setMode] = useState<'auto' | 'review'>('review');
  const [ontology, setOntology] = useState<OntologySpec>(result.ontology);
  const [evalMetrics] = useState<EvalMetrics | null>(result.eval_report);
  const [status, setStatus] = useState<string>('draft');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Dialog state
  const [editNodeIdx, setEditNodeIdx] = useState<number | null>(null);
  const [showAddNode, setShowAddNode] = useState(false);
  const [editRelIdx, setEditRelIdx] = useState<number | null>(null);
  const [showAddRel, setShowAddRel] = useState(false);

  // KG Build state
  const [buildJob, setBuildJob] = useState<KGBuildResponse | null>(null);
  const [buildLoading, setBuildLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // CSV Import state
  const [csvSessionId, setCsvSessionId] = useState<string | null>(null);
  const [csvTables, setCsvTables] = useState<CSVTableSummary[]>([]);
  const [csvUploading, setCsvUploading] = useState(false);
  const csvInputRef = useRef<HTMLInputElement>(null);

  const locked = status === 'approved';
  const versionId = result.version_id;
  const nodeNames = ontology.node_types.map((n) => n.name);

  function showError(msg: string) {
    setError(msg);
    setSuccessMsg(null);
    setTimeout(() => setError(null), 5000);
  }

  function showSuccess(msg: string) {
    setSuccessMsg(msg);
    setError(null);
    setTimeout(() => setSuccessMsg(null), 5000);
  }

  // ── Save (PUT) ──────────────────────────────────────────────────

  async function handleSave() {
    if (!versionId) {
      showError('No version ID available (PG may be offline)');
      return;
    }
    setLoading(true);
    try {
      const resp = await updateVersion(versionId, ontology);
      if (resp.updated) {
        showSuccess('Saved successfully');
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setLoading(false);
    }
  }

  // ── Approve (POST) ──────────────────────────────────────────────

  async function handleApprove() {
    if (!versionId) {
      showError('No version ID available (PG may be offline)');
      return;
    }
    setLoading(true);
    try {
      const resp = await approveVersion(versionId);
      setStatus(resp.status);
      showSuccess('Approved!');
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Approve failed');
    } finally {
      setLoading(false);
    }
  }

  // ── Node CRUD ───────────────────────────────────────────────────

  function handleDeleteNode(idx: number) {
    setOntology((prev) => ({
      ...prev,
      node_types: prev.node_types.filter((_, i) => i !== idx),
    }));
  }

  function handleSaveNode(node: NodeType, idx: number | null) {
    setOntology((prev) => {
      const nodes = [...prev.node_types];
      if (idx !== null) {
        nodes[idx] = node;
      } else {
        nodes.push(node);
      }
      return { ...prev, node_types: nodes };
    });
  }

  // ── Relationship CRUD ──────────────────────────────────────────

  function handleDeleteRel(idx: number) {
    setOntology((prev) => ({
      ...prev,
      relationship_types: prev.relationship_types.filter((_, i) => i !== idx),
    }));
  }

  function handleReverseRel(idx: number) {
    setOntology((prev) => {
      const rels = [...prev.relationship_types];
      const rel = rels[idx];
      rels[idx] = {
        ...rel,
        source_node: rel.target_node,
        target_node: rel.source_node,
      };
      return { ...prev, relationship_types: rels };
    });
  }

  function handleSaveRel(rel: RelationshipType, idx: number | null) {
    setOntology((prev) => {
      const rels = [...prev.relationship_types];
      if (idx !== null) {
        rels[idx] = rel;
      } else {
        rels.push(rel);
      }
      return { ...prev, relationship_types: rels };
    });
  }

  // ── CSV Upload ────────────────────────────────────────────────────

  async function handleCSVUpload(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setCsvUploading(true);
    setCsvTables([]);
    setCsvSessionId(null);
    try {
      const files = Array.from(fileList);
      const resp = await uploadCSVFiles(files, erd);
      setCsvSessionId(resp.csv_session_id);
      setCsvTables(resp.tables);
      showSuccess(`CSV uploaded: ${resp.tables.length} table(s) validated`);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'CSV upload failed');
    } finally {
      setCsvUploading(false);
      if (csvInputRef.current) csvInputRef.current.value = '';
    }
  }

  // ── KG Build ────────────────────────────────────────────────────

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  async function handleBuildKG() {
    if (!versionId) {
      showError('No version ID available');
      return;
    }
    setBuildLoading(true);
    try {
      const job = await startKGBuild(versionId, erd, csvSessionId ?? undefined);
      setBuildJob(job);

      // Start polling every 2 seconds
      pollRef.current = setInterval(async () => {
        try {
          const updated = await getKGBuildStatus(job.build_job_id);
          setBuildJob(updated);
          if (updated.status === 'succeeded' || updated.status === 'failed') {
            stopPolling();
            setBuildLoading(false);
            if (updated.status === 'succeeded') {
              showSuccess(
                `KG built: ${updated.progress?.nodes_created ?? 0} nodes, ${updated.progress?.relationships_created ?? 0} relationships (${updated.progress?.duration_seconds ?? 0}s)`,
              );
            } else if (updated.error) {
              showError(`Build failed at ${updated.error.stage}: ${updated.error.message}`);
            }
          }
        } catch {
          stopPolling();
          setBuildLoading(false);
        }
      }, 2000);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Build KG failed');
      setBuildLoading(false);
    }
  }

  const buildDisabled = status !== 'approved' || buildLoading || !versionId;

  // ── Render ──────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold">Ontology Review</h2>
          <Badge variant={locked ? 'default' : 'secondary'}>
            {status}
          </Badge>
          {versionId && (
            <span className="text-sm text-muted-foreground">v{versionId}</span>
          )}
        </div>
        <ModeToggle mode={mode} onModeChange={setMode} disabled={locked} />
      </div>

      {/* Messages */}
      {error && (
        <div className="rounded-lg border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {successMsg && (
        <div className="rounded-lg border border-green-500 bg-green-50 p-3 text-sm text-green-800">
          {successMsg}
        </div>
      )}

      {/* Evaluation */}
      {evalMetrics && <EvalCard metrics={evalMetrics} />}

      {/* Auto Mode */}
      {mode === 'auto' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Auto Mode</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-lg border p-3">
                <p className="text-muted-foreground">Node Types</p>
                <p className="text-2xl font-bold">{ontology.node_types.length}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-muted-foreground">Relationships</p>
                <p className="text-2xl font-bold">{ontology.relationship_types.length}</p>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              Stage: <strong>{result.stage}</strong>
            </p>
            <div className="flex gap-2">
              <Button onClick={handleApprove} disabled={locked || loading}>
                {locked ? 'Approved' : loading ? 'Approving...' : 'Auto Approve'}
              </Button>
              <Button
                variant="outline"
                onClick={handleBuildKG}
                disabled={buildDisabled}
              >
                {buildLoading ? 'Building...' : csvSessionId ? 'Build KG (CSV)' : 'Build KG'}
              </Button>
              {buildJob?.status === 'succeeded' && onGoToQuery && (
                <Button onClick={onGoToQuery}>
                  Q&A
                </Button>
              )}
            </div>
            {locked && (
              <div className="space-y-2">
                <p className="text-sm font-medium">CSV Data (optional)</p>
                <div className="flex items-center gap-2">
                  <input
                    ref={csvInputRef}
                    type="file"
                    multiple
                    accept=".csv"
                    onChange={(e) => handleCSVUpload(e.target.files)}
                    disabled={csvUploading}
                    className="text-sm file:mr-2 file:rounded file:border-0 file:bg-primary file:px-3 file:py-1 file:text-sm file:text-primary-foreground hover:file:bg-primary/90"
                  />
                  {csvUploading && <span className="text-sm text-muted-foreground animate-pulse">Validating...</span>}
                </div>
                {csvTables.length > 0 && (
                  <div className="space-y-1">
                    {csvTables.map((t) => (
                      <div key={t.table_name} className="flex items-center gap-2 text-sm">
                        <Badge variant="default" className="bg-green-600">{t.table_name}</Badge>
                        <span>{t.row_count} rows</span>
                        <span className="text-muted-foreground">({t.columns.join(', ')})</span>
                        {t.warnings.map((w, i) => (
                          <span key={i} className="text-yellow-600 text-xs">{w}</span>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
                {!csvSessionId && csvTables.length === 0 && !csvUploading && (
                  <p className="text-xs text-muted-foreground">No CSV uploaded — will use sample data</p>
                )}
              </div>
            )}
            {buildJob && (
              <div className="mt-3 rounded-lg border p-3 text-sm">
                <p className="font-medium">
                  Build: <span className="capitalize">{buildJob.status}</span>
                </p>
                {(buildJob.status === 'queued' || buildJob.status === 'running') && (
                  <p className="text-muted-foreground animate-pulse">Processing...</p>
                )}
                {buildJob.status === 'succeeded' && buildJob.progress && (
                  <p className="text-green-700">
                    {buildJob.progress.nodes_created} nodes, {buildJob.progress.relationships_created} relationships ({buildJob.progress.duration_seconds}s)
                  </p>
                )}
                {buildJob.status === 'failed' && buildJob.error && (
                  <p className="text-destructive">
                    {buildJob.error.stage}: {buildJob.error.message}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Review Mode */}
      {mode === 'review' && (
        <>
          <Tabs defaultValue="nodes">
            <TabsList>
              <TabsTrigger value="nodes">Nodes</TabsTrigger>
              <TabsTrigger value="relationships">Relationships</TabsTrigger>
              <TabsTrigger value="changes">Changes</TabsTrigger>
            </TabsList>

            <TabsContent value="nodes" className="mt-4">
              <NodeTypeTable
                nodes={ontology.node_types}
                locked={locked}
                onEdit={(i) => setEditNodeIdx(i)}
                onDelete={handleDeleteNode}
                onAdd={() => setShowAddNode(true)}
              />
            </TabsContent>

            <TabsContent value="relationships" className="mt-4">
              <RelationshipTable
                relationships={ontology.relationship_types}
                locked={locked}
                onEdit={(i) => setEditRelIdx(i)}
                onDelete={handleDeleteRel}
                onReverse={handleReverseRel}
                onAdd={() => setShowAddRel(true)}
              />
            </TabsContent>

            <TabsContent value="changes" className="mt-4">
              <DiffPanel diffs={result.llm_diffs} stage={result.stage} />
            </TabsContent>
          </Tabs>

          {/* CSV Upload (visible after approval) */}
          {locked && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">CSV Data (optional)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <input
                    ref={csvInputRef}
                    type="file"
                    multiple
                    accept=".csv"
                    onChange={(e) => handleCSVUpload(e.target.files)}
                    disabled={csvUploading}
                    className="text-sm file:mr-2 file:rounded file:border-0 file:bg-primary file:px-3 file:py-1 file:text-sm file:text-primary-foreground hover:file:bg-primary/90"
                  />
                  {csvUploading && <span className="text-sm text-muted-foreground animate-pulse">Validating...</span>}
                </div>
                {csvTables.length > 0 && (
                  <div className="space-y-1">
                    {csvTables.map((t) => (
                      <div key={t.table_name} className="flex items-center gap-2 text-sm">
                        <Badge variant="default" className="bg-green-600">{t.table_name}</Badge>
                        <span>{t.row_count} rows</span>
                        <span className="text-muted-foreground">({t.columns.join(', ')})</span>
                        {t.warnings.map((w, i) => (
                          <span key={i} className="text-yellow-600 text-xs">{w}</span>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
                {!csvSessionId && csvTables.length === 0 && !csvUploading && (
                  <p className="text-xs text-muted-foreground">No CSV uploaded — will use sample data</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Action buttons */}
          <div className="flex gap-2">
            <Button onClick={handleSave} disabled={locked || loading} variant="outline">
              {loading ? 'Saving...' : 'Save'}
            </Button>
            <Button onClick={handleApprove} disabled={locked || loading}>
              {locked ? 'Approved' : loading ? 'Approving...' : 'Approve'}
            </Button>
            <Button
              variant="outline"
              onClick={handleBuildKG}
              disabled={buildDisabled}
            >
              {buildLoading ? 'Building...' : csvSessionId ? 'Build KG (CSV)' : 'Build KG'}
            </Button>
            {buildJob?.status === 'succeeded' && onGoToQuery && (
              <Button onClick={onGoToQuery}>
                Q&A
              </Button>
            )}
          </div>
          {buildJob && (
            <div className="rounded-lg border p-3 text-sm">
              <p className="font-medium">
                Build: <span className="capitalize">{buildJob.status}</span>
              </p>
              {(buildJob.status === 'queued' || buildJob.status === 'running') && (
                <p className="text-muted-foreground animate-pulse">Processing...</p>
              )}
              {buildJob.status === 'succeeded' && buildJob.progress && (
                <p className="text-green-700">
                  {buildJob.progress.nodes_created} nodes, {buildJob.progress.relationships_created} relationships ({buildJob.progress.duration_seconds}s)
                </p>
              )}
              {buildJob.status === 'failed' && buildJob.error && (
                <p className="text-destructive">
                  {buildJob.error.stage}: {buildJob.error.message}
                </p>
              )}
            </div>
          )}
        </>
      )}

      {/* Edit Node Dialog */}
      {(editNodeIdx !== null || showAddNode) && (
        <EditNodeDialog
          node={editNodeIdx !== null ? ontology.node_types[editNodeIdx] : null}
          open
          onClose={() => {
            setEditNodeIdx(null);
            setShowAddNode(false);
          }}
          onSave={(node) => {
            handleSaveNode(node, editNodeIdx);
            setEditNodeIdx(null);
            setShowAddNode(false);
          }}
        />
      )}

      {/* Edit Relationship Dialog */}
      {(editRelIdx !== null || showAddRel) && (
        <EditRelationshipDialog
          relationship={
            editRelIdx !== null ? ontology.relationship_types[editRelIdx] : null
          }
          nodeNames={nodeNames}
          open
          onClose={() => {
            setEditRelIdx(null);
            setShowAddRel(false);
          }}
          onSave={(rel) => {
            handleSaveRel(rel, editRelIdx);
            setEditRelIdx(null);
            setShowAddRel(false);
          }}
        />
      )}
    </div>
  );
}
