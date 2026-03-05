import { ArrowUpDown, ChevronDown, ChevronUp } from 'lucide-react';
import { TableHead } from '@/components/ui/table';
import { cn } from '@/lib/utils';

interface SortableTableHeadProps {
  children: React.ReactNode;
  active: boolean;
  direction: 'asc' | 'desc' | null;
  onSort: () => void;
  className?: string;
}

export default function SortableTableHead({
  children,
  active,
  direction,
  onSort,
  className,
}: SortableTableHeadProps) {
  return (
    <TableHead
      className={cn('cursor-pointer select-none hover:bg-muted/50', className)}
      onClick={onSort}
    >
      <div className="flex items-center gap-1">
        {children}
        {active && direction === 'asc' && <ChevronUp className="h-4 w-4" />}
        {active && direction === 'desc' && <ChevronDown className="h-4 w-4" />}
        {!active && <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground/50" />}
      </div>
    </TableHead>
  );
}
