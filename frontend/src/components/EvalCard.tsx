import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { EvalMetrics } from '@/types/ontology';

interface EvalCardProps {
  metrics: EvalMetrics;
}

function MetricItem({ label, value, format = 'percent' }: {
  label: string;
  value: number | null;
  format?: 'percent' | 'number';
}) {
  let display: string;
  if (value === null) {
    display = 'N/A';
  } else if (format === 'percent') {
    display = `${(value * 100).toFixed(1)}%`;
  } else {
    display = String(value);
  }

  return (
    <div className="rounded-lg border p-3 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-bold">{display}</p>
    </div>
  );
}

export default function EvalCard({ metrics }: EvalCardProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Evaluation Metrics</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricItem label="Critical Error Rate" value={metrics.critical_error_rate} />
          <MetricItem label="FK Coverage" value={metrics.fk_relationship_coverage} />
          <MetricItem label="Direction Accuracy" value={metrics.direction_accuracy} />
          <MetricItem label="LLM Adoption" value={metrics.llm_adoption_rate} />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricItem label="Nodes (Gen)" value={metrics.node_count_generated} format="number" />
          <MetricItem label="Nodes (Golden)" value={metrics.node_count_golden} format="number" />
          <MetricItem label="Rels (Gen)" value={metrics.relationship_count_generated} format="number" />
          <MetricItem label="Rels (Golden)" value={metrics.relationship_count_golden} format="number" />
        </div>
      </CardContent>
    </Card>
  );
}
