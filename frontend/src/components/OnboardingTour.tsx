import { useState, useEffect } from 'react';

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

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true);
    }
  }, []);

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, '1');
    setVisible(false);
  }

  if (!visible) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-50"
        onClick={dismiss}
      />
      {/* Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-background rounded-xl shadow-lg border max-w-md w-full p-6 space-y-4">
          {/* Step indicator */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {step + 1} / {STEPS.length}
            </span>
            <button
              onClick={dismiss}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              건너뛰기 (Skip)
            </button>
          </div>

          {/* Progress dots */}
          <div className="flex gap-1.5 justify-center">
            {STEPS.map((_, i) => (
              <div
                key={i}
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
                className="px-4 py-2 rounded-lg text-sm border hover:bg-muted transition-colors"
              >
                이전
              </button>
            )}
            {isLast ? (
              <button
                onClick={dismiss}
                className="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                시작하기
              </button>
            ) : (
              <button
                onClick={() => setStep(step + 1)}
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
