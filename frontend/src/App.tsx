import { useState, lazy, Suspense } from 'react';
import UploadPage from '@/pages/UploadPage';
import ReviewPage from '@/pages/ReviewPage';
import type { ERDSchema, OntologyGenerateResponse } from '@/types/ontology';

const QueryPage = lazy(() => import('@/pages/QueryPage'));
const ExplorePage = lazy(() => import('@/pages/ExplorePage'));

type Page = 'upload' | 'review' | 'query' | 'explore';

function App() {
  const [page, setPage] = useState<Page>('upload');
  const [prevPage, setPrevPage] = useState<Page>('upload');
  const [generateResult, setGenerateResult] = useState<OntologyGenerateResponse | null>(null);
  const [erd, setErd] = useState<ERDSchema | null>(null);

  function handleGenerated(result: OntologyGenerateResponse, erdData: ERDSchema) {
    setGenerateResult(result);
    setErd(erdData);
    setPage('review');
  }

  function handleBackToUpload() {
    setPage('upload');
    setGenerateResult(null);
    setErd(null);
  }

  function handleGoToQuery() {
    setPage('query');
  }

  function handleBackToReview() {
    setPage('review');
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between px-4 py-3">
          <h1 className="text-lg font-semibold">GraphRAG 온톨로지 빌더</h1>
          <nav className="flex items-center gap-2">
            {page === 'review' && (
              <button
                onClick={handleBackToUpload}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                &larr; 새 업로드
              </button>
            )}
            <button
              onClick={() => {
                setPrevPage(page);
                setPage('explore');
              }}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                page === 'explore'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'
              }`}
            >
              그래프 탐색
            </button>
          </nav>
        </div>
      </header>
      <main className={page === 'explore' ? '' : 'container mx-auto px-4 py-8'}>
        {page === 'upload' && <UploadPage onGenerated={handleGenerated} />}
        {page === 'review' && generateResult && erd && (
          <ReviewPage result={generateResult} erd={erd} onGoToQuery={handleGoToQuery} />
        )}
        {page === 'query' && (
          <Suspense fallback={<div className="flex items-center justify-center h-40 text-muted-foreground">로딩 중...</div>}>
            <QueryPage onBack={handleBackToReview} />
          </Suspense>
        )}
        {page === 'explore' && (
          <Suspense fallback={<div className="flex items-center justify-center h-40 text-muted-foreground">로딩 중...</div>}>
            <ExplorePage onBack={() => setPage(prevPage)} />
          </Suspense>
        )}
      </main>
    </div>
  );
}

export default App;
