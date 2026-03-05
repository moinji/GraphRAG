import { Badge } from '@/components/ui/badge';
import type { CSVTableSummary } from '@/types/ontology';

interface CSVUploadSectionProps {
  csvInputRef: React.RefObject<HTMLInputElement | null>;
  csvUploading: boolean;
  csvTables: CSVTableSummary[];
  csvErrors: string[];
  csvWarnings: string[];
  csvSessionId: string | null;
  onUpload: (files: FileList | null) => void;
}

export default function CSVUploadSection({
  csvInputRef,
  csvUploading,
  csvTables,
  csvErrors,
  csvWarnings,
  csvSessionId,
  onUpload,
}: CSVUploadSectionProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          ref={csvInputRef}
          type="file"
          multiple
          accept=".csv"
          onChange={(e) => onUpload(e.target.files)}
          disabled={csvUploading}
          className="text-sm file:mr-2 file:rounded file:border-0 file:bg-primary file:px-3 file:py-1 file:text-sm file:text-primary-foreground hover:file:bg-primary/90"
        />
        {csvUploading && (
          <span className="text-sm text-muted-foreground animate-pulse">검증 중...</span>
        )}
      </div>

      {/* 성공한 테이블 목록 */}
      {csvTables.length > 0 && (
        <div className="space-y-1">
          {csvTables.map((t) => (
            <div key={t.table_name} className="flex items-center gap-2 text-sm">
              <Badge variant="default" className="bg-green-600">{t.table_name}</Badge>
              <span>{t.row_count} rows</span>
              <span className="text-muted-foreground">({t.columns.join(', ')})</span>
              {t.warnings.map((w, i) => (
                <span key={i} className="text-yellow-600 text-xs">{w}</span>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* 실패한 파일별 에러 목록 */}
      {csvErrors.length > 0 && (
        <div className="space-y-1 rounded-lg border border-destructive/30 bg-destructive/5 p-2">
          <p className="text-xs font-medium text-destructive">검증 오류:</p>
          {csvErrors.map((err, i) => (
            <p key={i} className="text-xs text-destructive">• {err}</p>
          ))}
        </div>
      )}

      {/* 누락 테이블 경고 (non-blocking) */}
      {csvWarnings.length > 0 && (
        <div className="space-y-1 rounded-lg border border-yellow-400/30 bg-yellow-50 p-2">
          <p className="text-xs font-medium text-yellow-700">경고:</p>
          {csvWarnings.map((w, i) => (
            <p key={i} className="text-xs text-yellow-700">• {w}</p>
          ))}
        </div>
      )}

      {/* 기본 안내 */}
      {!csvSessionId && csvTables.length === 0 && csvErrors.length === 0 && !csvUploading && (
        <p className="text-xs text-muted-foreground">CSV 미업로드 — 샘플 데이터 사용</p>
      )}
    </div>
  );
}
