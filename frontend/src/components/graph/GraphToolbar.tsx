import { useEffect, useRef, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { LAYOUT_LABELS, type LayoutName } from './graph-layouts';

const DEMO_QUESTIONS = [
  { label: 'Q1', text: '고객 김민수가 주문한 상품은?' },
  { label: 'Q2', text: '김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?' },
  { label: 'Q3', text: '가장 많이 팔린 카테고리 Top 3는?' },
  { label: 'Q4', text: '김민수와 이영희가 공통으로 구매한 상품은?' },
  { label: 'Q5', text: '쿠폰 사용 주문과 미사용 주문의 평균 금액 비교' },
];

interface GraphToolbarProps {
  searchTerm: string;
  onSearchChange: (term: string) => void;
  layout: LayoutName;
  onLayoutChange: (layout: LayoutName) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  totalNodes: number;
  totalEdges: number;
  truncated: boolean;
  onDemoQuestion?: (question: string) => void;
  demoQueryLoading?: boolean;
}

export default function GraphToolbar({
  searchTerm,
  onSearchChange,
  layout,
  onLayoutChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  totalNodes,
  totalEdges,
  truncated,
  onDemoQuestion,
  demoQueryLoading,
}: GraphToolbarProps) {
  const [localSearch, setLocalSearch] = useState(searchTerm);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      onSearchChange(localSearch);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [localSearch, onSearchChange]);

  return (
    <div className="flex items-center gap-3 border-b bg-background px-4 py-2">
      {/* Search */}
      <Input
        placeholder="Search nodes..."
        value={localSearch}
        onChange={(e) => setLocalSearch(e.target.value)}
        className="w-56"
      />

      {/* Demo Q&A dropdown */}
      {onDemoQuestion && (
        <Select
          onValueChange={(v) => onDemoQuestion(v)}
          disabled={demoQueryLoading}
        >
          <SelectTrigger className="w-56">
            <SelectValue placeholder={demoQueryLoading ? "Loading..." : "Demo Q&A..."} />
          </SelectTrigger>
          <SelectContent>
            {DEMO_QUESTIONS.map((q) => (
              <SelectItem key={q.label} value={q.text}>
                [{q.label}] {q.text}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {/* Layout selector */}
      <Select value={layout} onValueChange={(v) => onLayoutChange(v as LayoutName)}>
        <SelectTrigger className="w-48">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(LAYOUT_LABELS) as LayoutName[]).map((key) => (
            <SelectItem key={key} value={key}>
              {LAYOUT_LABELS[key]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Zoom controls */}
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" onClick={onZoomIn} title="Zoom In">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        </Button>
        <Button variant="outline" size="icon-sm" onClick={onZoomOut} title="Zoom Out">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        </Button>
        <Button variant="outline" size="icon-sm" onClick={onFitView} title="Fit View">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/></svg>
        </Button>
      </div>

      {/* Stats badges */}
      <div className="ml-auto flex items-center gap-2">
        <Badge variant="secondary">{totalNodes} nodes</Badge>
        <Badge variant="secondary">{totalEdges} edges</Badge>
        {truncated && (
          <Badge variant="outline" className="text-amber-600 border-amber-300">
            Truncated
          </Badge>
        )}
      </div>
    </div>
  );
}
