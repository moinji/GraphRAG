import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { uploadDocuments, listDocuments, deleteDocument } from '@/api/client';
import type { DocumentInfo } from '@/types/ontology';

interface DocumentsPageProps {
  onBack: () => void;
  onGoToQuery: () => void;
}

const ACCEPTED_TYPES = '.pdf,.docx,.md,.markdown,.html,.htm,.txt';

export default function DocumentsPage({ onBack, onGoToQuery }: DocumentsPageProps) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [successMsg, setSuccessMsg] = useState('');
  const [polling, setPolling] = useState(false);

  const refreshDocs = useCallback(async () => {
    try {
      const res = await listDocuments();
      setDocuments(res.documents);
      // Continue polling if any doc is still processing
      const hasProcessing = res.documents.some((d) => d.status === 'processing');
      setPolling(hasProcessing);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    refreshDocs();
  }, [refreshDocs]);

  // Poll while documents are processing
  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(refreshDocs, 3000);
    return () => clearInterval(interval);
  }, [polling, refreshDocs]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setErrors([]);
    setSuccessMsg('');

    try {
      const res = await uploadDocuments(Array.from(files));
      if (res.errors.length > 0) {
        setErrors(res.errors);
      }
      if (res.total_queued > 0) {
        setSuccessMsg(`${res.total_queued}개 파일 처리 시작`);
        setPolling(true);
        // Refresh after short delay to catch new docs
        setTimeout(refreshDocs, 1000);
      }
    } catch (err) {
      setErrors([err instanceof Error ? err.message : 'Upload failed']);
    } finally {
      setUploading(false);
      // Reset file input
      e.target.value = '';
    }
  }

  async function handleDelete(docId: number) {
    try {
      await deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.document_id !== docId));
    } catch (err) {
      setErrors([err instanceof Error ? err.message : 'Delete failed']);
    }
  }

  const readyCount = documents.filter((d) => d.status === 'ready').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">문서 관리</h2>
        <div className="flex items-center gap-2">
          {readyCount > 0 && (
            <Button onClick={onGoToQuery} variant="default" size="sm">
              Q&A (Mode C) &rarr;
            </Button>
          )}
          <button
            onClick={onBack}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; 돌아가기
          </button>
        </div>
      </div>

      {/* Upload section */}
      <div className="rounded-lg border border-dashed p-6 text-center">
        <p className="text-sm text-muted-foreground mb-3">
          PDF, DOCX, Markdown, HTML, TXT 파일을 업로드하세요
        </p>
        <label className="inline-block cursor-pointer">
          <input
            type="file"
            multiple
            accept={ACCEPTED_TYPES}
            onChange={handleUpload}
            disabled={uploading}
            aria-label="문서 파일 선택"
            className="sr-only"
          />
          <span
            role="button"
            tabIndex={0}
            aria-busy={uploading}
            className={`inline-flex items-center px-4 py-2 rounded-md text-sm font-medium cursor-pointer transition-colors ${
              uploading
                ? 'bg-muted text-muted-foreground cursor-not-allowed'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            }`}
          >
            {uploading ? '업로드 중...' : '파일 선택'}
          </span>
        </label>
      </div>

      {/* Messages */}
      {successMsg && (
        <div role="status" aria-live="polite" className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-800">
          {successMsg}
        </div>
      )}
      {errors.length > 0 && (
        <div role="alert" className="rounded-md bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive space-y-1">
          {errors.map((err, i) => (
            <p key={i}>{err}</p>
          ))}
        </div>
      )}

      {/* Document list */}
      {documents.length === 0 ? (
        <p className="text-center text-muted-foreground py-8">
          업로드된 문서가 없습니다
        </p>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm" aria-label="문서 목록">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2 font-medium">파일명</th>
                <th className="text-left px-4 py-2 font-medium">타입</th>
                <th className="text-right px-4 py-2 font-medium">크기</th>
                <th className="text-right px-4 py-2 font-medium">청크</th>
                <th className="text-center px-4 py-2 font-medium">상태</th>
                <th className="text-right px-4 py-2 font-medium">작업</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {documents.map((doc) => (
                <tr key={doc.document_id} className="hover:bg-muted/30">
                  <td className="px-4 py-2 font-medium">{doc.filename}</td>
                  <td className="px-4 py-2">
                    <Badge variant="outline" className="text-xs uppercase">
                      {doc.file_type}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right text-muted-foreground">
                    {formatSize(doc.file_size)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {doc.chunk_count > 0 ? doc.chunk_count : '-'}
                  </td>
                  <td className="px-4 py-2 text-center">
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleDelete(doc.document_id)}
                      aria-label={`${doc.filename} 삭제`}
                      className="text-xs text-destructive hover:text-destructive/80"
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      {documents.length > 0 && (
        <p className="text-xs text-muted-foreground text-center">
          전체 {documents.length}개 문서 | 처리 완료 {readyCount}개 |{' '}
          총 {documents.reduce((sum, d) => sum + d.chunk_count, 0)}개 청크
        </p>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'ready') {
    return <Badge className="bg-green-600 text-white text-xs">완료</Badge>;
  }
  if (status === 'processing') {
    return <Badge className="bg-yellow-500 text-white text-xs animate-pulse" aria-label="처리 진행 중">처리중</Badge>;
  }
  return <Badge variant="destructive" className="text-xs">실패</Badge>;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}
