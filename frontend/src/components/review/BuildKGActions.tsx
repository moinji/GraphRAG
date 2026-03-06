import { Button } from '@/components/ui/button';
import type { KGBuildResponse } from '@/types/ontology';

interface BuildKGActionsProps {
  buildDisabled: boolean;
  buildLoading: boolean;
  resetLoading: boolean;
  csvSessionId: string | null;
  buildJob: KGBuildResponse | null;
  onBuildKG: () => void;
  onResetGraph: () => void;
  onGoToQuery?: () => void;
}

export default function BuildKGActions({
  buildDisabled,
  buildLoading,
  resetLoading,
  csvSessionId,
  buildJob,
  onBuildKG,
  onResetGraph,
  onGoToQuery,
}: BuildKGActionsProps) {
  return (
    <>
      <div className="flex gap-2">
        <Button
          variant="outline"
          onClick={onBuildKG}
          disabled={buildDisabled}
        >
          {buildLoading ? '빌드 중...' : csvSessionId ? 'KG 빌드 (CSV)' : 'KG 빌드'}
        </Button>
        <Button
          variant="outline"
          onClick={onResetGraph}
          disabled={resetLoading || buildLoading}
          className="text-destructive border-destructive/30 hover:bg-destructive/10"
        >
          {resetLoading ? '초기화 중...' : '그래프 초기화'}
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
            빌드: <span className="capitalize">{buildJob.status}</span>
          </p>
          {(buildJob.status === 'queued' || buildJob.status === 'running') && buildJob.progress && (
            <div>
              <div className="flex items-center gap-2 text-muted-foreground">
                <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all duration-500"
                    style={{ width: `${(buildJob.progress.step_number / buildJob.progress.total_steps) * 100}%` }}
                  />
                </div>
                <span className="text-xs tabular-nums">{buildJob.progress.step_number}/{buildJob.progress.total_steps}</span>
              </div>
              <p className="text-muted-foreground animate-pulse mt-1">
                {buildJob.progress.current_step === 'data_generation' && '데이터 생성 중...'}
                {buildJob.progress.current_step === 'fk_verification' && 'FK 무결성 검증 중...'}
                {buildJob.progress.current_step === 'neo4j_load' && 'Neo4j에 로딩 중...'}
                {(!buildJob.progress.current_step || buildJob.progress.current_step === 'starting') && '시작 중...'}
              </p>
            </div>
          )}
          {(buildJob.status === 'queued' || buildJob.status === 'running') && !buildJob.progress && (
            <p className="text-muted-foreground animate-pulse">대기 중...</p>
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
  );
}
