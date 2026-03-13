/**
 * Tests for DocumentsPage component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import DocumentsPage from '@/pages/DocumentsPage';

// Mock API calls
vi.mock('@/api/client', () => ({
  uploadDocuments: vi.fn(),
  listDocuments: vi.fn().mockResolvedValue({ documents: [] }),
  deleteDocument: vi.fn(),
}));

describe('DocumentsPage', () => {
  const onBack = vi.fn();
  const onGoToQuery = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders heading', () => {
    render(<DocumentsPage onBack={onBack} onGoToQuery={onGoToQuery} />);
    expect(screen.getByText('문서 관리')).toBeInTheDocument();
  });

  it('renders back button', () => {
    render(<DocumentsPage onBack={onBack} onGoToQuery={onGoToQuery} />);
    const backBtn = screen.getByText(/돌아가기/);
    expect(backBtn).toBeInTheDocument();
  });

  it('renders file upload area', () => {
    render(<DocumentsPage onBack={onBack} onGoToQuery={onGoToQuery} />);
    expect(screen.getByText(/PDF, DOCX, Markdown/)).toBeInTheDocument();
    expect(screen.getByLabelText('문서 파일 선택')).toBeInTheDocument();
  });

  it('shows empty state when no documents', () => {
    render(<DocumentsPage onBack={onBack} onGoToQuery={onGoToQuery} />);
    expect(screen.getByText('업로드된 문서가 없습니다')).toBeInTheDocument();
  });

  it('file input accepts correct types', () => {
    render(<DocumentsPage onBack={onBack} onGoToQuery={onGoToQuery} />);
    const input = screen.getByLabelText('문서 파일 선택') as HTMLInputElement;
    expect(input.accept).toContain('.pdf');
    expect(input.accept).toContain('.docx');
    expect(input.accept).toContain('.md');
  });

  it('has proper accessibility attributes', () => {
    render(<DocumentsPage onBack={onBack} onGoToQuery={onGoToQuery} />);
    const uploadBtn = screen.getByRole('button', { name: /파일 선택/ });
    expect(uploadBtn).toHaveAttribute('tabindex', '0');
  });
});
