import { useState, useEffect, useCallback, useRef } from 'react';

const STORAGE_KEY = 'graphrag_onboarding_done';

const STEPS = [
  {
    title: 'DDL 업로드',
    desc: 'SQL DDL 파일을 업로드하면 테이블과 FK를 자동 분석합니다.',
    descEn: 'Upload a SQL DDL file to auto-analyze tables and foreign keys.',
  },
  {
    title: '온톨로지 생성',
    desc: 'FK 규칙 기반으로 노드와 관계를 자동 매핑합니다. LLM 보강도 선택 가능합니다.',
    descEn: 'Auto-map nodes and relationships from FK rules. LLM enrichment is optional.',
  },
  {
    title: '리뷰 & KG 빌드',
    desc: '생성된 온톨로지를 리뷰하고, 승인 후 Neo4j 지식 그래프를 빌드합니다.',
    descEn: 'Review the ontology, approve it, then build the Neo4j knowledge graph.',
  },
  {
    title: 'Q&A 질의',
    desc: '지식 그래프에 자연어로 질문하세요. 한글/영어 모두 지원합니다.',
    descEn: 'Ask natural language questions. Both Korean and English are supported.',
  },
] as const;

export default function OnboardingTour() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true);
    }
  }, []);

  // Focus the dialog when it becomes visible
  useEffect(() => {
    if (visible) {
      dialogRef.current?.focus();
    }
  }, [visible, step]);

  const dismiss = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
  }, []);

  // Keyboard navigation: Escape to dismiss, Arrow keys to navigate
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      dismiss();
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      setStep((s) => Math.min(s + 1, STEPS.length - 1));
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      setStep((s) => Math.max(s - 1, 0));
    }
  }, [dismiss]);

  if (!visible) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-50"
        onClick={dismiss}
        aria-hidden="true"
      />
      {/* Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label={`온보딩 가이드: ${current.title}`}
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          className="bg-background rounded-xl shadow-lg border max-w-md w-full p-6 space-y-4 outline-none"
        >
          {/* Step indicator */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {step + 1} / {STEPS.length}
            </span>
            <button
              onClick={dismiss}
              aria-label="온보딩 건너뛰기"
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              건너뛰기 (Skip)
            </button>
          </div>

          {/* Progress dots */}
          <div className="flex gap-1.5 justify-center" role="group" aria-label="진행 단계">
            {STEPS.map((s, i) => (
              <div
                key={i}
                role="presentation"
                aria-current={i === step ? 'step' : undefined}
                aria-label={`${i + 1}단계: ${s.title}`}
                className={`h-1.5 rounded-full transition-all ${
                  i === step ? 'w-6 bg-primary' : 'w-1.5 bg-muted-foreground/30'
                }`}
              />
            ))}
          </div>

          {/* Content */}
          <div className="text-center space-y-2">
            <div className="mx-auto w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-xl font-bold text-primary">
              {step + 1}
            </div>
            <h3 className="text-lg font-semibold">{current.title}</h3>
            <p className="text-sm text-muted-foreground">{current.desc}</p>
            <p className="text-xs text-muted-foreground/70">{current.descEn}</p>
          </div>

          {/* Navigation */}
          <div className="flex gap-2 justify-end">
            {step > 0 && (
              <button
                onClick={() => setStep(step - 1)}
                aria-label="이전 단계"
                className="px-4 py-2 rounded-lg text-sm border hover:bg-muted transition-colors"
              >
                이전
              </button>
            )}
            {isLast ? (
              <button
                onClick={dismiss}
                aria-label="온보딩 완료 후 시작"
                className="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                시작하기
              </button>
            ) : (
              <button
                onClick={() => setStep(step + 1)}
                aria-label="다음 단계"
                className="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                다음
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
