import { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
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
import OWLPanel from '@/components/review/OWLPanel';
import SchemaDiffPanel from '@/components/review/SchemaDiffPanel';
import { updateVersion, approveVersion, startKGBuild, uploadCSVFiles, resetGraph, generateMapping, updateMapping, APIError } from '@/api/client';
import { streamKGBuild } from '@/api/sse';
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

  // Dialog state
  const [editNodeIdx, setEditNodeIdx] = useState<number | null>(null);
  const [showAddNode, setShowAddNode] = useState(false);
  const [editRelIdx, setEditRelIdx] = useState<number | null>(null);
  const [showAddRel, setShowAddRel] = useState(false);

  // KG Build state
  const [buildJob, setBuildJob] = useState<KGBuildResponse | null>(null);
  const [buildLoading, setBuildLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const pollRef = useRef<(() => void) | null>(null);

  // CSV Import state
  const [csvSessionId, setCsvSessionId] = useState<string | null>(null);
  const [csvTables, setCsvTables] = useState<CSVTableSummary[]>([]);
  const [csvErrors, setCsvErrors] = useState<string[]>([]);
  const [csvWarnings, setCsvWarnings] = useState<string[]>([]);
  const [csvUploading, setCsvUploading] = useState(false);
  const csvInputRef = useRef<HTMLInputElement>(null);

  // Mapping state
  const [yamlContent, setYamlContent] = useState<string | null>(null);
  const [yamlLoading, setYamlLoading] = useState(false);
  const [yamlEditing, setYamlEditing] = useState(false);
  const [yamlDraft, setYamlDraft] = useState('');
  const [mappingWarnings, setMappingWarnings] = useState<string[]>([]);

  const locked = status === 'approved';
  const versionId = result.version_id;
  const nodeNames = ontology.node_types.map((n) => n.name);

  // ── Save (PUT) ──────────────────────────────────────────────────

  async function handleSave() {
    if (!versionId) {
      toast.error('No version ID available (PG may be offline)');
      return;
    }
    setLoading(true);
    try {
      const resp = await updateVersion(versionId, ontology);
      if (resp.updated) {
        toast.success('Saved successfully');
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setLoading(false);
    }
  }

  // ── Approve (POST) ──────────────────────────────────────────────

  async function handleApprove() {
    if (!versionId) {
      toast.error('No version ID available (PG may be offline)');
      return;
    }
    setLoading(true);
    try {
      const resp = await approveVersion(versionId);
      setStatus(resp.status);
      toast.success('Approved!');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Approve failed');
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
        toast.success(`CSV: ${resp.tables.length} table(s) OK, ${resp.errors.length} error(s)`);
      } else {
        toast.success(`CSV uploaded: ${resp.tables.length} table(s) validated`);
      }
    } catch (e) {
      if (e instanceof APIError && e.errors.length > 0) {
        setCsvErrors(e.errors);
      }
      toast.error(e instanceof Error ? e.message : 'CSV upload failed');
    } finally {
      setCsvUploading(false);
      if (csvInputRef.current) csvInputRef.current.value = '';
    }
  }

  // ── YAML Mapping ────────────────────────────────────────────────

  async function handleGenerateMapping() {
    if (!versionId) return;
    setYamlLoading(true);
    setMappingWarnings([]);
    try {
      const resp = await generateMapping(versionId);
      setYamlContent(resp.yaml_content);
      setYamlDraft(resp.yaml_content);
      if (resp.validation_warnings.length > 0) {
        setMappingWarnings(resp.validation_warnings);
      }
      toast.success(`Mapping generated: ${resp.triples_map_count} nodes, ${resp.relationship_map_count} relationships`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Mapping generation failed');
    } finally {
      setYamlLoading(false);
    }
  }

  async function handleSaveMapping() {
    if (!versionId) return;
    setYamlLoading(true);
    try {
      const resp = await updateMapping(versionId, yamlDraft);
      setYamlContent(yamlDraft);
      setYamlEditing(false);
      if (resp.validation_warnings?.length > 0) {
        setMappingWarnings(resp.validation_warnings);
      }
      toast.success('Mapping saved');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Save mapping failed');
    } finally {
      setYamlLoading(false);
    }
  }

  // ── KG Build ────────────────────────────────────────────────────

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      pollRef.current();
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  async function handleBuildKG(useMapping = false) {
    if (!versionId) {
      toast.error('No version ID available');
      return;
    }
    setBuildLoading(true);
    try {
      const job = await startKGBuild(versionId, erd, csvSessionId ?? undefined, useMapping || undefined);
      setBuildJob(job);

      const cleanup = streamKGBuild(
        job.build_job_id,
        (progress) => setBuildJob(progress),
        (final) => {
          setBuildJob(final);
          setBuildLoading(false);
          if (final.status === 'succeeded') {
            toast.success(
              `KG built: ${final.progress?.nodes_created ?? 0} nodes, ${final.progress?.relationships_created ?? 0} relationships (${final.progress?.duration_seconds ?? 0}s)`,
            );
          } else if (final.error) {
            toast.error(`Build failed at ${final.error.stage}: ${final.error.message}`);
          }
        },
        (error) => {
          setBuildLoading(false);
          toast.error(error.message);
        },
      );
      pollRef.current = cleanup;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Build KG failed');
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
      toast.success(`Graph reset: ${resp.deleted_nodes} nodes, ${resp.deleted_edges} edges deleted`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Reset failed');
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
          {result.detected_domain && (
            <Badge variant="outline" className="border-purple-400 text-purple-600">
              {result.detected_domain}
            </Badge>
          )}
          {result.quality_score != null && (
            <Badge
              variant="outline"
              className={
                result.quality_score >= 0.8
                  ? 'border-green-500 text-green-600'
                  : result.quality_score >= 0.5
                    ? 'border-amber-500 text-amber-600'
                    : 'border-red-500 text-red-600'
              }
            >
              Quality {Math.round(result.quality_score * 100)}%
            </Badge>
          )}
        </div>
        <ModeToggle mode={mode} onModeChange={setMode} disabled={locked} />
      </div>

      {/* Backend warnings */}
      {result.warnings?.length > 0 && (
        <div role="alert" className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-800 space-y-1">
          {result.warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
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
              <TabsTrigger value="mapping">매핑 (YAML)</TabsTrigger>
              <TabsTrigger value="changes">변경 사항</TabsTrigger>
              <TabsTrigger value="owl">OWL / SHACL</TabsTrigger>
              <TabsTrigger value="evolution">스키마 진화</TabsTrigger>
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

            <TabsContent value="mapping" className="mt-4">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">YAML 매핑 (R2RML 호환)</CardTitle>
                    <div className="flex gap-2">
                      {!yamlContent ? (
                        <Button
                          onClick={handleGenerateMapping}
                          disabled={yamlLoading || !locked}
                          size="sm"
                          variant="outline"
                        >
                          {yamlLoading ? '생성 중...' : '매핑 생성'}
                        </Button>
                      ) : (
                        <>
                          {yamlEditing ? (
                            <>
                              <Button onClick={handleSaveMapping} disabled={yamlLoading} size="sm">
                                {yamlLoading ? '저장 중...' : '저장'}
                              </Button>
                              <Button
                                onClick={() => { setYamlEditing(false); setYamlDraft(yamlContent); }}
                                size="sm"
                                variant="outline"
                              >
                                취소
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button onClick={() => setYamlEditing(true)} size="sm" variant="outline">
                                편집
                              </Button>
                              <Button onClick={handleGenerateMapping} disabled={yamlLoading} size="sm" variant="ghost">
                                재생성
                              </Button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {!locked && (
                    <p className="text-sm text-muted-foreground">
                      온톨로지를 승인한 후 매핑을 생성할 수 있습니다.
                    </p>
                  )}
                  {mappingWarnings.length > 0 && (
                    <div className="mb-3 rounded-lg border border-amber-400 bg-amber-50 p-2 text-xs text-amber-800 space-y-1">
                      {mappingWarnings.map((w, i) => <p key={i}>{w}</p>)}
                    </div>
                  )}
                  {yamlContent && !yamlEditing && (
                    <pre className="rounded-lg border bg-muted p-3 text-xs overflow-x-auto max-h-96 overflow-y-auto font-mono">
                      {yamlContent}
                    </pre>
                  )}
                  {yamlEditing && (
                    <textarea
                      value={yamlDraft}
                      onChange={(e) => setYamlDraft(e.target.value)}
                      className="w-full rounded-lg border p-3 text-xs font-mono bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                      rows={20}
                      spellCheck={false}
                    />
                  )}
                  {yamlContent && !yamlEditing && locked && (
                    <div className="mt-3 pt-3 border-t">
                      <Button
                        onClick={() => handleBuildKG(true)}
                        disabled={buildLoading}
                        size="sm"
                      >
                        {buildLoading ? '빌드 중...' : 'Build KG (매핑 적용)'}
                      </Button>
                      <p className="mt-1 text-xs text-muted-foreground">
                        현재 YAML 매핑 설정을 적용하여 Knowledge Graph를 빌드합니다.
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="changes" className="mt-4">
              <DiffPanel diffs={result.llm_diffs} stage={result.stage} />
            </TabsContent>

            <TabsContent value="owl" className="mt-4">
              <OWLPanel versionId={versionId} locked={locked} />
            </TabsContent>

            <TabsContent value="evolution" className="mt-4">
              <SchemaDiffPanel
                currentVersionId={versionId ? versionId - 1 : null}
                targetVersionId={versionId}
                erd={erd}
                onMigrationComplete={() => {
                  toast.success('Migration complete — KG updated');
                }}
              />
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
