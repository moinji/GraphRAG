import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { getNodeColor } from './graph-styles';

interface GraphFilterSidebarProps {
  allLabels: string[];
  visibleLabels: Set<string>;
  onToggleLabel: (label: string) => void;
  allEdgeTypes: string[];
  visibleEdgeTypes: Set<string>;
  onToggleEdgeType: (edgeType: string) => void;
  stats: { node_counts: Record<string, number>; edge_counts: Record<string, number> } | null;
}

export default function GraphFilterSidebar({
  allLabels,
  visibleLabels,
  onToggleLabel,
  allEdgeTypes,
  visibleEdgeTypes,
  onToggleEdgeType,
  stats,
}: GraphFilterSidebarProps) {
  return (
    <div className="flex h-full w-56 flex-col border-r bg-background overflow-y-auto">
      {/* Node types */}
      <div className="px-3 py-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
          노드 타입
        </h3>
        <ul className="space-y-1">
          {allLabels.map((label) => (
            <li key={label}>
              <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent">
                <Checkbox
                  checked={visibleLabels.has(label)}
                  onCheckedChange={() => onToggleLabel(label)}
                />
                <div
                  className="size-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: getNodeColor(label) }}
                />
                <span className="truncate">{label}</span>
                {stats?.node_counts[label] != null && (
                  <Badge variant="secondary" className="ml-auto text-[10px]">
                    {stats.node_counts[label]}
                  </Badge>
                )}
              </label>
            </li>
          ))}
        </ul>
      </div>

      {/* Edge types */}
      <div className="border-t px-3 py-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
          엣지 타입
        </h3>
        <ul className="space-y-1">
          {allEdgeTypes.map((edgeType) => (
            <li key={edgeType}>
              <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent">
                <Checkbox
                  checked={visibleEdgeTypes.has(edgeType)}
                  onCheckedChange={() => onToggleEdgeType(edgeType)}
                />
                <span className="truncate text-xs">{edgeType}</span>
                {stats?.edge_counts[edgeType] != null && (
                  <Badge variant="secondary" className="ml-auto text-[10px]">
                    {stats.edge_counts[edgeType]}
                  </Badge>
                )}
              </label>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
