/**
 * Tests for BuildKGActions component.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import BuildKGActions from '@/components/review/BuildKGActions';

describe('BuildKGActions', () => {
  const defaultProps = {
    buildDisabled: false,
    buildLoading: false,
    resetLoading: false,
    csvSessionId: null,
    buildJob: null,
    onBuildKG: vi.fn(),
    onResetGraph: vi.fn(),
  };

  it('renders build and reset buttons', () => {
    render(<BuildKGActions {...defaultProps} />);
    expect(screen.getByText('KG 빌드')).toBeInTheDocument();
    expect(screen.getByText('그래프 초기화')).toBeInTheDocument();
  });

  it('shows CSV label when csvSessionId set', () => {
    render(<BuildKGActions {...defaultProps} csvSessionId="abc123" />);
    expect(screen.getByText('KG 빌드 (CSV)')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    render(<BuildKGActions {...defaultProps} buildLoading={true} />);
    expect(screen.getByText('빌드 중...')).toBeInTheDocument();
  });

  it('disables build button when buildDisabled', () => {
    render(<BuildKGActions {...defaultProps} buildDisabled={true} />);
    expect(screen.getByText('KG 빌드')).toBeDisabled();
  });

  it('calls onBuildKG on click', () => {
    const onBuildKG = vi.fn();
    render(<BuildKGActions {...defaultProps} onBuildKG={onBuildKG} />);
    fireEvent.click(screen.getByText('KG 빌드'));
    expect(onBuildKG).toHaveBeenCalledOnce();
  });

  it('calls onResetGraph on click', () => {
    const onResetGraph = vi.fn();
    render(<BuildKGActions {...defaultProps} onResetGraph={onResetGraph} />);
    fireEvent.click(screen.getByText('그래프 초기화'));
    expect(onResetGraph).toHaveBeenCalledOnce();
  });

  it('shows Q&A button when build succeeded', () => {
    const onGoToQuery = vi.fn();
    render(
      <BuildKGActions
        {...defaultProps}
        buildJob={{ build_job_id: '1', version_id: 1, status: 'succeeded', progress: null, error: null, started_at: null, completed_at: null }}
        onGoToQuery={onGoToQuery}
      />,
    );
    const qaBtn = screen.getByText('Q&A');
    expect(qaBtn).toBeInTheDocument();
    fireEvent.click(qaBtn);
    expect(onGoToQuery).toHaveBeenCalledOnce();
  });

  it('shows error when build failed', () => {
    render(
      <BuildKGActions
        {...defaultProps}
        buildJob={{
          build_job_id: '1',
          version_id: 1,
          status: 'failed',
          progress: null,
          error: { stage: 'neo4j_load', message: 'Connection refused', detail: '' },
          started_at: null,
          completed_at: null,
        }}
      />,
    );
    expect(screen.getByText(/Connection refused/)).toBeInTheDocument();
  });

  it('shows progress bar when running', () => {
    render(
      <BuildKGActions
        {...defaultProps}
        buildJob={{
          build_job_id: '1',
          version_id: 1,
          status: 'running',
          progress: {
            step_number: 1,
            total_steps: 3,
            current_step: 'data_generation',
            nodes_created: 0,
            relationships_created: 0,
            duration_seconds: 0,
            error_count: 0,
          },
          error: null,
          started_at: null,
          completed_at: null,
        }}
      />,
    );
    expect(screen.getByText('1/3')).toBeInTheDocument();
    expect(screen.getByText('데이터 생성 중...')).toBeInTheDocument();
  });
});
