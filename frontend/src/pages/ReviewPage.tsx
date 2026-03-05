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
import CSVUploadSection from '@/components/review/CSVUploadSection';
import BuildKGActions from '@/components/review/BuildKGActions';
import { updateVersion, approveVersion, startKGBuild, getKGBuildStatus, uploadCSVFiles, resetGraph, APIError } from '@/api/client';
import { BUILD_POLL_INTERVAL_MS, SUCCESS_MSG_TIMEOUT_MS } from '@/constants';
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
  const [resetLoading, setResetLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // CSV Import state
  const [csvSessionId, setCsvSessionId] = useState<string | null>(null);
  const [csvTables, setCsvTables] = useState<CSVTableSummary[]>([]);
  const [csvErrors, setCsvErrors] = useState<string[]>([]);
  const [csvWarnings, setCsvWarnings] = useState<string[]>([]);
  const [csvUploading, setCsvUploading] = useState(false);
  const csvInputRef = useRef<HTMLInputElement>(null);

  const locked = status === 'approved';
  const versionId = result.version_id;
  const nodeNames = ontology.node_types.map((n) => n.name);

  function showError(msg: string) {
    setError(msg);
    setSuccessMsg(null);
    // 에러는 auto-dismiss하지 않음 — 다음 액션 시 자연 소멸
  }

  function showSuccess(msg: string) {
    setSuccessMsg(msg);
    setError(null);
    setTimeout(() => setSuccessMsg(null), SUCCESS_MSG_TIMEOUT_MS);
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
    setCsvErrors([]);
    setCsvWarnings([]);
    setCsvSessionId(null);
    try {
      const files = Array.from(fileList);
      const resp = await uploadCSVFiles(files, erd);
      setCsvSessionId(resp.csv_session_id);
      setCsvTables(resp.tables);
      if (resp.errors?.length > 0) setCsvErrors(resp.errors);
      if (resp.warnings?.length > 0) setCsvWarnings(resp.warnings);
      // 부분 성공: 유효 파일은 세션 저장, 실패 파일은 에러로 표시
      if (resp.errors?.length > 0) {
        showSuccess(`CSV: ${resp.tables.length} table(s) OK, ${resp.errors.length} error(s)`);
      } else {
        showSuccess(`CSV uploaded: ${resp.tables.length} table(s) validated`);
      }
    } catch (e) {
      if (e instanceof APIError && e.errors.length > 0) {
        setCsvErrors(e.errors);
      }
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
      }, BUILD_POLL_INTERVAL_MS);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Build KG failed');
      setBuildLoading(false);
    }
  }

  const buildDisabled = status !== 'approved' || buildLoading || !versionId;

  async function handleResetGraph() {
    if (!window.confirm('그래프를 초기화하시겠습니까? Neo4j의 모든 노드와 엣지가 삭제됩니다.')) return;
    setResetLoading(true);
    try {
      const resp = await resetGraph();
      setBuildJob(null);
      showSuccess(`Graph reset: ${resp.deleted_nodes} nodes, ${resp.deleted_edges} edges deleted`);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Reset failed');
    } finally {
      setResetLoading(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold">온톨로지 리뷰 (Review)</h2>
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
            <CardTitle className="text-base">자동 모드 (Auto)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-lg border p-3">
                <p className="text-muted-foreground">노드 타입 (Node Types)</p>
                <p className="text-2xl font-bold">{ontology.node_types.length}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-muted-foreground">관계 (Relationships)</p>
                <p className="text-2xl font-bold">{ontology.relationship_types.length}</p>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              Stage: <strong>{result.stage}</strong>
            </p>
            <div className="flex gap-2">
              <Button onClick={handleApprove} disabled={locked || loading}>
                {locked ? '승인됨' : loading ? '승인 중...' : '자동 승인'}
              </Button>
            </div>
            {locked && (
              <div className="space-y-2">
                <p className="text-sm font-medium">CSV 데이터 (선택사항)</p>
                <CSVUploadSection
                  csvInputRef={csvInputRef}
                  csvUploading={csvUploading}
                  csvTables={csvTables}
                  csvErrors={csvErrors}
                  csvWarnings={csvWarnings}
                  csvSessionId={csvSessionId}
                  onUpload={handleCSVUpload}
                />
              </div>
            )}
            <BuildKGActions
              buildDisabled={buildDisabled}
              buildLoading={buildLoading}
              resetLoading={resetLoading}
              csvSessionId={csvSessionId}
              buildJob={buildJob}
              onBuildKG={handleBuildKG}
              onResetGraph={handleResetGraph}
              onGoToQuery={onGoToQuery}
            />
          </CardContent>
        </Card>
      )}

      {/* Review Mode */}
      {mode === 'review' && (
        <>
          <Tabs defaultValue="nodes">
            <TabsList>
              <TabsTrigger value="nodes">노드</TabsTrigger>
              <TabsTrigger value="relationships">관계</TabsTrigger>
              <TabsTrigger value="changes">변경 사항</TabsTrigger>
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
                <CardTitle className="text-base">CSV 데이터 (선택사항)</CardTitle>
              </CardHeader>
              <CardContent>
                <CSVUploadSection
                  csvInputRef={csvInputRef}
                  csvUploading={csvUploading}
                  csvTables={csvTables}
                  csvErrors={csvErrors}
                  csvWarnings={csvWarnings}
                  csvSessionId={csvSessionId}
                  onUpload={handleCSVUpload}
                />
              </CardContent>
            </Card>
          )}

          {/* Action buttons */}
          <div className="flex gap-2">
            <Button onClick={handleSave} disabled={locked || loading} variant="outline">
              {loading ? '저장 중...' : '저장'}
            </Button>
            <Button onClick={handleApprove} disabled={locked || loading}>
              {locked ? '승인됨' : loading ? '승인 중...' : '승인'}
            </Button>
          </div>
          <BuildKGActions
            buildDisabled={buildDisabled}
            buildLoading={buildLoading}
            resetLoading={resetLoading}
            csvSessionId={csvSessionId}
            buildJob={buildJob}
            onBuildKG={handleBuildKG}
            onResetGraph={handleResetGraph}
            onGoToQuery={onGoToQuery}
          />
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
