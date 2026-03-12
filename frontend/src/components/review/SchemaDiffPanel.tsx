import { useState } from 'react';
import { toast } from 'sonner';
import { computeOntologyDiff, computeImpact, startMigration, getMigrationStatus } from '@/api/client';
import type { ERDSchema, OntologyDiff, ImpactAnalysis, MigrationResponse } from '@/types/ontology';

interface Props {
  currentVersionId: number | null;
  targetVersionId: number | null;
  erd: ERDSchema | null;
  onMigrationComplete?: () => void;
}

const CHANGE_COLORS = {
  added: 'bg-green-100 text-green-800 border-green-300',
  removed: 'bg-red-100 text-red-800 border-red-300',
  modified: 'bg-yellow-100 text-yellow-800 border-yellow-300',
};

const CHANGE_LABELS = {
  added: '+',
  removed: '-',
  modified: '~',
};

export default function SchemaDiffPanel({ currentVersionId, targetVersionId, erd, onMigrationComplete }: Props) {
  const [diff, setDiff] = useState<OntologyDiff | null>(null);
  const [impact, setImpact] = useState<ImpactAnalysis | null>(null);
  const [migration, setMigration] = useState<MigrationResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const canDiff = currentVersionId != null && targetVersionId != null && currentVersionId !== targetVersionId;

  async function handleComputeDiff() {
    if (!canDiff) return;
    setLoading(true);
    try {
      const result = await computeOntologyDiff(currentVersionId!, targetVersionId!);
      setDiff(result);
      setImpact(null);
      setMigration(null);
    } catch (err: any) {
      toast.error(err.message || 'Diff computation failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyzeImpact() {
    if (!canDiff) return;
    setLoading(true);
    try {
      const result = await computeImpact(currentVersionId!, targetVersionId!);
      setDiff(result.diff);
      setImpact(result.impact);
    } catch (err: any) {
      toast.error(err.message || 'Impact analysis failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleMigrate(dryRun: boolean) {
    if (!canDiff || !erd) return;
    setLoading(true);
    try {
      const job = await startMigration(currentVersionId!, targetVersionId!, erd, dryRun);
      setMigration(job);

      // Poll
      const poll = setInterval(async () => {
        try {
          const status = await getMigrationStatus(job.migration_job_id);
          setMigration(status);
          if (status.diff) setDiff(status.diff);
          if (status.impact) setImpact(status.impact);
          if (status.status === 'succeeded' || status.status === 'failed') {
            clearInterval(poll);
            setLoading(false);
            if (status.status === 'succeeded') {
              toast.success(dryRun ? 'Dry run complete' : 'Migration succeeded!');
              if (!dryRun) onMigrationComplete?.();
            } else {
              toast.error(`Migration failed: ${status.error?.message || 'Unknown error'}`);
            }
          }
        } catch {
          clearInterval(poll);
          setLoading(false);
        }
      }, 2000);
    } catch (err: any) {
      toast.error(err.message || 'Migration failed');
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <h3 className="text-lg font-semibold">Schema Evolution</h3>
        {currentVersionId && targetVersionId && (
          <span className="text-sm text-gray-500">
            v{currentVersionId} → v{targetVersionId}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={handleComputeDiff}
          disabled={!canDiff || loading}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          Compute Diff
        </button>
        <button
          onClick={handleAnalyzeImpact}
          disabled={!canDiff || loading}
          className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
        >
          Analyze Impact
        </button>
        <button
          onClick={() => handleMigrate(true)}
          disabled={!canDiff || !erd || loading}
          className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50"
        >
          Dry Run
        </button>
        <button
          onClick={() => handleMigrate(false)}
          disabled={!canDiff || !erd || loading || !diff}
          className="px-3 py-1.5 text-sm bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50"
        >
          Migrate
        </button>
      </div>

      {/* Diff Results */}
      {diff && (
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <span className="font-medium">Diff Summary:</span>
            <span className="text-sm">{diff.summary}</span>
            {diff.is_breaking && (
              <span className="px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 rounded">
                BREAKING
              </span>
            )}
          </div>

          {/* Node Diffs */}
          {diff.node_diffs.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-1">Node Types</h4>
              <div className="space-y-1">
                {diff.node_diffs.map((nd) => (
                  <div key={nd.name} className={`flex items-center gap-2 px-2 py-1 rounded border text-sm ${CHANGE_COLORS[nd.change_type as keyof typeof CHANGE_COLORS]}`}>
                    <span className="font-mono font-bold w-4">{CHANGE_LABELS[nd.change_type as keyof typeof CHANGE_LABELS]}</span>
                    <span className="font-medium">{nd.name}</span>
                    {nd.source_table && <span className="text-xs opacity-70">({nd.source_table})</span>}
                    {nd.property_changes.length > 0 && (
                      <span className="text-xs">
                        [{nd.property_changes.map((pc) => `${CHANGE_LABELS[pc.change_type as keyof typeof CHANGE_LABELS]}${pc.name}`).join(', ')}]
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Relationship Diffs */}
          {diff.relationship_diffs.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-1">Relationships</h4>
              <div className="space-y-1">
                {diff.relationship_diffs.map((rd) => (
                  <div key={rd.name} className={`flex items-center gap-2 px-2 py-1 rounded border text-sm ${CHANGE_COLORS[rd.change_type as keyof typeof CHANGE_COLORS]}`}>
                    <span className="font-mono font-bold w-4">{CHANGE_LABELS[rd.change_type as keyof typeof CHANGE_LABELS]}</span>
                    <span className="font-medium">{rd.name}</span>
                    <span className="text-xs opacity-70">{rd.source_node} → {rd.target_node}</span>
                    {rd.endpoint_changed && (
                      <span className="px-1 py-0.5 text-xs bg-red-200 text-red-800 rounded">endpoint changed</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Impact Analysis */}
      {impact && (
        <div className="border rounded-lg p-4 space-y-2 bg-purple-50">
          <h4 className="text-sm font-semibold">Impact Analysis</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>Affected Nodes: <span className="font-bold">{impact.total_affected_nodes}</span></div>
            <div>Affected Rels: <span className="font-bold">{impact.total_affected_relationships}</span></div>
          </div>
          {Object.entries(impact.affected_node_counts).length > 0 && (
            <div className="text-xs text-gray-600">
              {Object.entries(impact.affected_node_counts).map(([k, v]) => `${k}: ${v}`).join(', ')}
            </div>
          )}
          {impact.warnings.length > 0 && (
            <div className="text-xs text-orange-700">
              {impact.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
            </div>
          )}
          <div className="text-xs text-gray-500">
            Estimated: ~{impact.estimated_duration_seconds}s
          </div>
        </div>
      )}

      {/* Migration Progress */}
      {migration && migration.status !== 'queued' && (
        <div className={`border rounded-lg p-4 space-y-2 ${
          migration.status === 'succeeded' ? 'bg-green-50' :
          migration.status === 'failed' ? 'bg-red-50' : 'bg-blue-50'
        }`}>
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold">Migration</h4>
            <span className={`px-2 py-0.5 text-xs rounded ${
              migration.status === 'succeeded' ? 'bg-green-200 text-green-800' :
              migration.status === 'failed' ? 'bg-red-200 text-red-800' :
              'bg-blue-200 text-blue-800'
            }`}>
              {migration.status}
            </span>
          </div>
          {migration.progress && (
            <div className="text-sm">
              <div className="w-full bg-gray-200 rounded h-2 mb-2">
                <div
                  className="bg-blue-600 h-2 rounded transition-all"
                  style={{ width: `${(migration.progress.step_number / migration.progress.total_steps) * 100}%` }}
                />
              </div>
              <div className="grid grid-cols-3 gap-1 text-xs">
                <div>+{migration.progress.nodes_added} nodes</div>
                <div>-{migration.progress.nodes_removed} nodes</div>
                <div>+{migration.progress.relationships_added} rels</div>
                <div>-{migration.progress.relationships_removed} rels</div>
                <div>~{migration.progress.properties_modified} props</div>
                <div>{migration.progress.duration_seconds}s</div>
              </div>
            </div>
          )}
          {migration.error && (
            <div className="text-xs text-red-700">{migration.error.message}</div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!diff && !loading && (
        <p className="text-sm text-gray-500">
          Select two ontology versions to compare. The current version is automatically selected.
        </p>
      )}
    </div>
  );
}
