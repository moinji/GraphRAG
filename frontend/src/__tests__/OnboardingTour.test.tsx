/**
 * Tests for OnboardingTour component.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import OnboardingTour from '@/components/OnboardingTour';

const STORAGE_KEY = 'graphrag_onboarding_done';

describe('OnboardingTour', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('shows tour on first visit', () => {
    render(<OnboardingTour />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('hides tour when already completed', () => {
    localStorage.setItem(STORAGE_KEY, '1');
    render(<OnboardingTour />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('displays step 1 initially', () => {
    render(<OnboardingTour />);
    expect(screen.getByText('DDL 업로드')).toBeInTheDocument();
    expect(screen.getByText('1 / 4')).toBeInTheDocument();
  });

  it('navigates to next step', () => {
    render(<OnboardingTour />);
    fireEvent.click(screen.getByLabelText('다음 단계'));
    expect(screen.getByText('온톨로지 생성')).toBeInTheDocument();
    expect(screen.getByText('2 / 4')).toBeInTheDocument();
  });

  it('navigates back to previous step', () => {
    render(<OnboardingTour />);
    fireEvent.click(screen.getByLabelText('다음 단계'));
    fireEvent.click(screen.getByLabelText('이전 단계'));
    expect(screen.getByText('DDL 업로드')).toBeInTheDocument();
  });

  it('shows start button on last step', () => {
    render(<OnboardingTour />);
    // Navigate to last step
    fireEvent.click(screen.getByLabelText('다음 단계')); // step 2
    fireEvent.click(screen.getByLabelText('다음 단계')); // step 3
    fireEvent.click(screen.getByLabelText('다음 단계')); // step 4
    expect(screen.getByText('시작하기')).toBeInTheDocument();
  });

  it('dismiss sets localStorage and hides', () => {
    render(<OnboardingTour />);
    fireEvent.click(screen.getByLabelText('온보딩 건너뛰기'));
    expect(localStorage.getItem(STORAGE_KEY)).toBe('1');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keyboard Escape dismisses tour', () => {
    render(<OnboardingTour />);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keyboard ArrowRight navigates forward', () => {
    render(<OnboardingTour />);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowRight' });
    expect(screen.getByText('온톨로지 생성')).toBeInTheDocument();
  });
});
