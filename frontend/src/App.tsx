import { useState } from 'react';
import UploadPage from '@/pages/UploadPage';
import ReviewPage from '@/pages/ReviewPage';
import type { ERDSchema, OntologyGenerateResponse } from '@/types/ontology';

type Page = 'upload' | 'review';

function App() {
  const [page, setPage] = useState<Page>('upload');
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

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between px-4 py-3">
          <h1 className="text-lg font-semibold">GraphRAG Ontology Builder</h1>
          {page === 'review' && (
            <button
              onClick={handleBackToUpload}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              &larr; New Upload
            </button>
          )}
        </div>
      </header>
      <main className="container mx-auto px-4 py-8">
        {page === 'upload' && <UploadPage onGenerated={handleGenerated} />}
        {page === 'review' && generateResult && erd && (
          <ReviewPage result={generateResult} erd={erd} />
        )}
      </main>
    </div>
  );
}

export default App;
