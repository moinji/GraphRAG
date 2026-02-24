import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface ModeToggleProps {
  mode: 'auto' | 'review';
  onModeChange: (mode: 'auto' | 'review') => void;
  disabled?: boolean;
}

export default function ModeToggle({ mode, onModeChange, disabled }: ModeToggleProps) {
  return (
    <Tabs value={mode} onValueChange={(v) => onModeChange(v as 'auto' | 'review')}>
      <TabsList>
        <TabsTrigger value="auto" disabled={disabled}>
          Auto
        </TabsTrigger>
        <TabsTrigger value="review" disabled={disabled}>
          Review
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}
