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
          <CardTitle className="text-base">LLM Changes</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No LLM changes (FK rules only applied).
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">LLM Changes ({diffs.length})</CardTitle>
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
