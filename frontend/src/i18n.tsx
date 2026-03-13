import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export type Locale = 'ko' | 'en';

const translations: Record<string, Record<Locale, string>> = {
  'app.title': { ko: 'GraphRAG 온톨로지 빌더', en: 'GraphRAG Ontology Builder' },
  'nav.dashboard': { ko: 'Dashboard', en: 'Dashboard' },
  'nav.documents': { ko: '문서 관리', en: 'Documents' },
  'nav.explore': { ko: '그래프 탐색', en: 'Graph Explorer' },
  'nav.newUpload': { ko: '새 업로드', en: 'New Upload' },
  'nav.back': { ko: '돌아가기', en: 'Back' },
  'common.loading': { ko: '로딩 중...', en: 'Loading...' },
  'common.error': { ko: '오류', en: 'Error' },
  'common.save': { ko: '저장', en: 'Save' },
  'common.cancel': { ko: '취소', en: 'Cancel' },
  'common.delete': { ko: '삭제', en: 'Delete' },
  'common.confirm': { ko: '확인', en: 'Confirm' },
  'query.placeholder': { ko: '질문을 입력하세요...', en: 'Enter your question...' },
  'query.send': { ko: '전송', en: 'Send' },
  'query.cached': { ko: '캐시됨', en: 'Cached' },
  'upload.title': { ko: 'DDL 업로드', en: 'Upload DDL' },
  'upload.description': { ko: 'DDL 파일을 업로드하여 온톨로지를 생성합니다.', en: 'Upload a DDL file to generate an ontology.' },
  'review.auto': { ko: '자동 (Auto)', en: 'Auto' },
  'review.review': { ko: '검토 (Review)', en: 'Review' },
  'review.approve': { ko: '승인', en: 'Approve' },
  'review.buildKG': { ko: 'KG 빌드', en: 'Build KG' },
  'review.resetGraph': { ko: '그래프 초기화', en: 'Reset Graph' },
  'dashboard.serviceStatus': { ko: '서비스 상태', en: 'Service Status' },
  'dashboard.totalQueries': { ko: '총 쿼리', en: 'Total Queries' },
  'dashboard.cacheHitRate': { ko: '캐시 히트율', en: 'Cache Hit Rate' },
  'dashboard.avgLatency': { ko: '평균 레이턴시', en: 'Avg Latency' },
  'dashboard.p95Latency': { ko: 'p95 레이턴시', en: 'p95 Latency' },
  'dashboard.llmUsage': { ko: 'LLM 사용량', en: 'LLM Usage' },
  'dashboard.recentQueries': { ko: '최근 쿼리', en: 'Recent Queries' },
};

interface I18nContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextType>({
  locale: 'ko',
  setLocale: () => {},
  t: (key) => key,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    const saved = localStorage.getItem('graphrag_locale');
    return (saved === 'en' ? 'en' : 'ko') as Locale;
  });

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem('graphrag_locale', l);
  }, []);

  const t = useCallback(
    (key: string) => {
      const entry = translations[key];
      if (!entry) return key;
      return entry[locale] ?? entry.ko ?? key;
    },
    [locale],
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}

export function LocaleToggle() {
  const { locale, setLocale } = useI18n();
  return (
    <button
      onClick={() => setLocale(locale === 'ko' ? 'en' : 'ko')}
      className="rounded-md px-2 py-1 text-xs font-medium border transition-colors hover:bg-accent"
      title={locale === 'ko' ? 'Switch to English' : '한국어로 전환'}
    >
      {locale === 'ko' ? 'EN' : '한국어'}
    </button>
  );
}
