import { useState } from 'react';
import UploadPage from '@/pages/UploadPage';
import ReviewPage from '@/pages/ReviewPage';
import QueryPage from '@/pages/QueryPage';
import ExplorePage from '@/pages/ExplorePage';
import type { ERDSchema, OntologyGenerateResponse } from '@/types/ontology';

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
          <h1 className="text-lg font-semibold">GraphRAG Ontology Builder</h1>
          <nav className="flex items-center gap-2">
            {page === 'review' && (
              <button
                onClick={handleBackToUpload}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                &larr; New Upload
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
              Explore Graph
            </button>
          </nav>
        </div>
      </header>
      <main className={page === 'explore' ? '' : 'container mx-auto px-4 py-8'}>
        {page === 'upload' && <UploadPage onGenerated={handleGenerated} />}
        {page === 'review' && generateResult && erd && (
          <ReviewPage result={generateResult} erd={erd} onGoToQuery={handleGoToQuery} />
        )}
        {page === 'query' && <QueryPage onBack={handleBackToReview} />}
        {page === 'explore' && <ExplorePage onBack={() => setPage(prevPage)} />}
      </main>
    </div>
  );
}

export default App;
