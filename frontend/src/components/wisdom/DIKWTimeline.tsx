import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import type { WisdomResponse } from '@/types/ontology';

const LEVEL_CONFIG = {
  data: { label: 'D', color: 'bg-slate-500', border: 'border-slate-400', text: 'text-slate-700' },
  information: { label: 'I', color: 'bg-blue-500', border: 'border-blue-400', text: 'text-blue-700' },
  knowledge: { label: 'K', color: 'bg-purple-500', border: 'border-purple-400', text: 'text-purple-700' },
  wisdom: { label: 'W', color: 'bg-amber-500', border: 'border-amber-400', text: 'text-amber-700' },
} as const;

const CONFIDENCE_STYLE = {
  high: 'bg-green-100 text-green-700 border-green-300',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-300',
  low: 'bg-red-100 text-red-700 border-red-300',
} as const;

interface Props {
  data: WisdomResponse;
  onRelatedQuery?: (q: string) => void;
}

export default function DIKWTimeline({ data, onRelatedQuery }: Props) {
  const [expandedLayers, setExpandedLayers] = useState<Set<string>>(new Set(['wisdom']));
  const [showQueries, setShowQueries] = useState(false);

  function toggleLayer(level: string) {
    setExpandedLayers((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  }

  return (
    <div className="mt-3 space-y-2">
      {/* Summary + badges */}
      <div className="flex items-start gap-2 flex-wrap">
        <Badge variant="outline" className="text-xs border-amber-500 text-amber-600">
          W {data.intent}
        </Badge>
        <Badge
          variant="outline"
          className={`text-xs ${CONFIDENCE_STYLE[data.confidence as keyof typeof CONFIDENCE_STYLE] || CONFIDENCE_STYLE.medium}`}
        >
          {data.confidence}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {data.latency_ms}ms | {data.llm_tokens_used} tokens
        </span>
      </div>

      {data.summary && (
        <p className="text-sm font-medium">{data.summary}</p>
      )}

      {/* DIKW layers */}
      <div className="relative pl-6">
        {/* vertical line */}
        <div className="absolute left-[11px] top-2 bottom-2 w-0.5 bg-gradient-to-b from-slate-400 via-blue-400 via-purple-400 to-amber-400" />

        {data.dikw_layers.map((layer) => {
          const cfg = LEVEL_CONFIG[layer.level as keyof typeof LEVEL_CONFIG];
          if (!cfg) return null;
          const expanded = expandedLayers.has(layer.level);

          return (
            <div key={layer.level} className="relative mb-2">
              {/* dot */}
              <div className={`absolute -left-6 top-1.5 w-5 h-5 rounded-full ${cfg.color} flex items-center justify-center`}>
                <span className="text-[10px] font-bold text-white">{cfg.label}</span>
              </div>

              {/* card */}
              <button
                onClick={() => toggleLayer(layer.level)}
                className={`w-full text-left rounded-lg border ${cfg.border} p-2.5 hover:bg-muted/50 transition-colors`}
              >
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold ${cfg.text}`}>
                    {layer.title}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {expanded ? '▼' : '▶'}
                  </span>
                </div>

                {expanded && (
                  <div className="mt-1.5 space-y-1">
                    <p className="text-sm whitespace-pre-wrap">{layer.content}</p>
                    {layer.evidence.length > 0 && (
                      <ul className="text-xs text-muted-foreground space-y-0.5 mt-1">
                        {layer.evidence.map((e, i) => (
                          <li key={i} className="flex items-start gap-1">
                            <span className="text-muted-foreground/60">-</span>
                            <span>{e}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </button>
            </div>
          );
        })}
      </div>

      {/* Action items */}
      {data.action_items.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5">
          <p className="text-xs font-semibold text-amber-700 mb-1">권장 행동</p>
          <ul className="space-y-0.5">
            {data.action_items.map((item, i) => (
              <li key={i} className="text-sm flex items-start gap-1.5">
                <span className="text-amber-500 mt-0.5 text-xs">&#9654;</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Related queries */}
      {data.related_queries.length > 0 && onRelatedQuery && (
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-muted-foreground">추가 탐색:</span>
          {data.related_queries.map((q, i) => (
            <button
              key={i}
              onClick={() => onRelatedQuery(q)}
              className="text-xs px-2 py-0.5 rounded-full border hover:bg-muted transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Cypher queries used */}
      {data.cypher_queries_used.length > 0 && (
        <div>
          <button
            onClick={() => setShowQueries(!showQueries)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {showQueries ? '▼' : '▶'} 사용된 쿼리 ({data.cypher_queries_used.length})
          </button>
          {showQueries && (
            <div className="mt-1 flex flex-wrap gap-1">
              {data.cypher_queries_used.map((q, i) => (
                <Badge key={i} variant="secondary" className="text-xs">
                  {q}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
