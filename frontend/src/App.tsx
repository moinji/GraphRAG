import { useState, lazy, Suspense } from 'react';
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom';
import UploadPage from '@/pages/UploadPage';
import ReviewPage from '@/pages/ReviewPage';
import OnboardingTour from '@/components/OnboardingTour';
import type { ERDSchema, OntologyGenerateResponse } from '@/types/ontology';

const QueryPage = lazy(() => import('@/pages/QueryPage'));
const ExplorePage = lazy(() => import('@/pages/ExplorePage'));
const DocumentsPage = lazy(() => import('@/pages/DocumentsPage'));

const Loading = () => (
  <div className="flex items-center justify-center h-40 text-muted-foreground">로딩 중...</div>
);

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [generateResult, setGenerateResult] = useState<OntologyGenerateResponse | null>(null);
  const [erd, setErd] = useState<ERDSchema | null>(null);

  function handleGenerated(result: OntologyGenerateResponse, erdData: ERDSchema) {
    setGenerateResult(result);
    setErd(erdData);
    navigate('/review');
  }

  function handleBackToUpload() {
    setGenerateResult(null);
    setErd(null);
    navigate('/');
  }

  function handleGoToQuery() {
    navigate('/query');
  }

  function handleBackToReview() {
    navigate('/review');
  }

  const isExplore = location.pathname === '/explore';

  return (
    <div className="min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md"
      >
        본문으로 건너뛰기
      </a>
      <OnboardingTour />
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between px-4 py-3">
          <h1
            className="text-lg font-semibold cursor-pointer"
            onClick={() => navigate('/')}
          >
            GraphRAG 온톨로지 빌더
          </h1>
          <nav className="flex items-center gap-2">
            {location.pathname === '/review' && (
              <button
                onClick={handleBackToUpload}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                &larr; 새 업로드
              </button>
            )}
            <button
              onClick={() => navigate('/documents')}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                location.pathname === '/documents'
                  ? 'bg-purple-600 text-white'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'
              }`}
            >
              문서 관리
            </button>
            <button
              onClick={() => navigate('/explore')}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                isExplore
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'
              }`}
            >
              그래프 탐색
            </button>
          </nav>
        </div>
      </header>
      <main id="main-content" className={isExplore ? '' : 'container mx-auto px-4 py-8'}>
        <Routes>
          <Route
            path="/"
            element={
              <UploadPage
                onGenerated={handleGenerated}
                onAutoComplete={(result, erdData) => {
                  setGenerateResult(result);
                  setErd(erdData);
                  navigate('/query');
                }}
              />
            }
          />
          <Route
            path="/review"
            element={
              generateResult && erd ? (
                <ReviewPage result={generateResult} erd={erd} onGoToQuery={handleGoToQuery} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/query"
            element={
              <Suspense fallback={<Loading />}>
                <QueryPage onBack={handleBackToReview} />
              </Suspense>
            }
          />
          <Route
            path="/documents"
            element={
              <Suspense fallback={<Loading />}>
                <DocumentsPage onBack={() => navigate(-1)} onGoToQuery={handleGoToQuery} />
              </Suspense>
            }
          />
          <Route
            path="/explore"
            element={
              <Suspense fallback={<Loading />}>
                <ExplorePage onBack={() => navigate(-1)} />
              </Suspense>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
