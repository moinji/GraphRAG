/**
 * SSE (Server-Sent Events) streaming client functions.
 */
import type { KGBuildResponse, QueryResponse } from '@/types/ontology';
import { getApiKey } from './client';

const BASE = '/api/v1';

// ── KG Build SSE (GET — native EventSource) ────────────────────

export function streamKGBuild(
  jobId: string,
  onProgress: (data: KGBuildResponse) => void,
  onDone: (data: KGBuildResponse) => void,
  onError: (error: Error) => void,
): () => void {
  const apiKey = getApiKey();
  const params = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : '';
  const es = new EventSource(`${BASE}/kg/build/${jobId}/stream${params}`);

  es.addEventListener('progress', (e) => {
    try {
      onProgress(JSON.parse((e as MessageEvent).data));
    } catch {
      // skip malformed event
    }
  });

  es.addEventListener('done', (e) => {
    try {
      onDone(JSON.parse((e as MessageEvent).data));
    } catch {
      // skip
    }
    es.close();
  });

  es.addEventListener('error', () => {
    // EventSource auto-reconnects; close on persistent error
    onError(new Error('SSE connection failed'));
    es.close();
  });

  return () => es.close();
}


// ── Query SSE (POST — fetch + ReadableStream) ──────────────────

interface StreamQueryCallbacks {
  onMetadata?: (data: Partial<QueryResponse>) => void;
  onToken?: (token: string) => void;
  onComplete: (data: QueryResponse) => void;
  onError: (error: Error) => void;
}

export function streamQuery(
  question: string,
  mode: string,
  { onMetadata, onToken, onComplete, onError }: StreamQueryCallbacks,
): AbortController {
  const controller = new AbortController();
  const apiKey = getApiKey();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) headers['X-API-Key'] = apiKey;

  fetch(`${BASE}/query/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ question, mode }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop()!; // keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);
              if (currentEvent === 'metadata' && onMetadata) {
                onMetadata(parsed);
              } else if (currentEvent === 'token' && onToken) {
                onToken(parsed.token);
              } else if (currentEvent === 'complete') {
                onComplete(parsed);
              } else if (currentEvent === 'error') {
                onError(new Error(parsed.detail || 'Stream error'));
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    });

  return controller;
}
