import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
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
  const [polling, setPolling] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  const refreshDocs = useCallback(async () => {
    try {
      const res = await listDocuments();
      setDocuments(res.documents);
      const hasProcessing = res.documents.some((d) => d.status === 'processing');
      setPolling(hasProcessing);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    refreshDocs();
  }, [refreshDocs]);

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(refreshDocs, 3000);
    return () => clearInterval(interval);
  }, [polling, refreshDocs]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      const res = await uploadDocuments(Array.from(files));
      if (res.errors.length > 0) {
        res.errors.forEach((err) => toast.error(err));
      }
      if (res.total_queued > 0) {
        toast.success(`${res.total_queued}개 파일 처리 시작`);
        setPolling(true);
        setTimeout(refreshDocs, 1000);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  }

  async function handleDelete(docId: number) {
    try {
      await deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.document_id !== docId));
      setDeleteConfirm(null);
      toast.success('문서가 삭제되었습니다');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  const readyCount = documents.filter((d) => d.status === 'ready').length;
  const totalChunks = documents.reduce((sum, d) => sum + d.chunk_count, 0);

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
        <div className="mx-auto w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-3">
          <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>
        <p className="text-sm text-muted-foreground mb-1">
          PDF, DOCX, Markdown, HTML, TXT 파일을 업로드하세요
        </p>
        <p className="text-xs text-muted-foreground/60 mb-3">
          드래그 앤 드롭 또는 클릭하여 선택
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

      {/* Document list */}
      {documents.length === 0 ? (
        <div className="text-center py-12 space-y-3">
          <div className="mx-auto w-16 h-16 rounded-full bg-muted flex items-center justify-center">
            <svg className="w-8 h-8 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-muted-foreground font-medium">업로드된 문서가 없습니다</p>
          <p className="text-xs text-muted-foreground/60">
            문서를 업로드하면 자동으로 청킹, 임베딩 처리 후 Mode C 질의에 활용됩니다
          </p>
        </div>
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
                    {deleteConfirm === doc.document_id ? (
                      <span className="inline-flex gap-1">
                        <button
                          onClick={() => handleDelete(doc.document_id)}
                          className="text-xs px-2 py-0.5 bg-destructive text-destructive-foreground rounded"
                        >
                          확인
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="text-xs px-2 py-0.5 border rounded"
                        >
                          취소
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setDeleteConfirm(doc.document_id)}
                        aria-label={`${doc.filename} 삭제`}
                        className="text-xs text-destructive hover:text-destructive/80"
                      >
                        삭제
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      {documents.length > 0 && (
        <div className="flex justify-center gap-4 text-xs text-muted-foreground">
          <span>전체 {documents.length}개 문서</span>
          <span>처리 완료 {readyCount}개</span>
          <span>총 {totalChunks}개 청크</span>
        </div>
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
