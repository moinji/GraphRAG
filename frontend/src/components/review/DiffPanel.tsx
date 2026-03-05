import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { LLMEnrichmentDiff } from '@/types/ontology';

interface DiffPanelProps {
  diffs: LLMEnrichmentDiff[];
  stage: string;
}

export default function DiffPanel({ diffs, stage }: DiffPanelProps) {
  if (stage === 'fk_only' || diffs.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">LLM 변경 사항</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            LLM 변경 없음 (FK 규칙만 적용됨)
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">LLM 변경 사항 ({diffs.length})</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {diffs.map((diff, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-1">
            <p className="text-sm font-medium">{diff.field}</p>
            <div className="flex gap-4 text-sm">
              {diff.before !== null && (
                <span className="line-through text-red-600">{diff.before}</span>
              )}
              {diff.after !== null && (
                <span className="text-green-600">{diff.after}</span>
              )}
            </div>
            {diff.reason && (
              <p className="text-xs text-muted-foreground">{diff.reason}</p>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
