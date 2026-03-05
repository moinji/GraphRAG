import type {
  CSVUploadResponse,
  ERDSchema,
  KGBuildResponse,
  OntologyApproveResponse,
  OntologyGenerateResponse,
  OntologySpec,
  OntologyUpdateResponse,
  OntologyVersionResponse,
  QueryResponse,
} from '@/types/ontology';
import type { GraphData, GraphResetResponse, GraphStats } from '@/types/graph';

const BASE = '/api/v1';

export class APIError extends Error {
  errors: string[];
  constructor(detail: string, errors: string[] = []) {
    super(detail);
    this.name = 'APIError';
    this.errors = errors;
  }
}

function validateResponse<T>(data: unknown, requiredKeys: string[]): data is T {
  if (typeof data !== 'object' || data === null) return false;
  return requiredKeys.every((key) => key in data);
}

async function request<T>(
  url: string,
  init?: RequestInit,
  requiredKeys?: string[],
): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new APIError(body.detail ?? `HTTP ${resp.status}`, body.errors ?? []);
  }
  const data = await resp.json();
  if (requiredKeys && !validateResponse<T>(data, requiredKeys)) {
    throw new APIError(
      `Unexpected API response shape from ${url} (missing: ${requiredKeys.filter((k) => !(k in (data as Record<string, unknown>))).join(', ')})`,
    );
  }
  return data as T;
}

/** Upload a DDL file and get the parsed ERD schema. */
export async function uploadDDL(file: File): Promise<ERDSchema> {
  const form = new FormData();
  form.append('file', file);
  return request<ERDSchema>(`${BASE}/ddl/upload`, {
    method: 'POST',
    body: form,
  });
}

/** Generate ontology from an ERD schema. */
export async function generateOntology(
  erd: ERDSchema,
  skipLlm: boolean,
): Promise<OntologyGenerateResponse> {
  return request<OntologyGenerateResponse>(
    `${BASE}/ontology/generate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ erd, skip_llm: skipLlm }),
    },
    ['ontology'],
  );
}

/** Get a specific ontology version. */
export async function getVersion(id: number): Promise<OntologyVersionResponse> {
  return request<OntologyVersionResponse>(
    `${BASE}/ontology/versions/${id}`,
  );
}

/** Update ontology for a draft version. */
export async function updateVersion(
  id: number,
  ontology: OntologySpec,
): Promise<OntologyUpdateResponse> {
  return request<OntologyUpdateResponse>(
    `${BASE}/ontology/versions/${id}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ontology }),
    },
  );
}

/** Approve a draft version. */
export async function approveVersion(
  id: number,
): Promise<OntologyApproveResponse> {
  return request<OntologyApproveResponse>(
    `${BASE}/ontology/versions/${id}/approve`,
    { method: 'POST' },
  );
}

/** Upload CSV files for KG build. */
export async function uploadCSVFiles(
  files: File[],
  erd: ERDSchema,
): Promise<CSVUploadResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append('files', file);
  }
  form.append('erd_json', JSON.stringify(erd));
  return request<CSVUploadResponse>(`${BASE}/csv/upload`, {
    method: 'POST',
    body: form,
  });
}

/** Start a KG build job for an approved version. */
export async function startKGBuild(
  versionId: number,
  erd: ERDSchema,
  csvSessionId?: string,
): Promise<KGBuildResponse> {
  const payload: Record<string, unknown> = { version_id: versionId, erd };
  if (csvSessionId) {
    payload.csv_session_id = csvSessionId;
  }
  return request<KGBuildResponse>(`${BASE}/kg/build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

/** Poll KG build job status. */
export async function getKGBuildStatus(
  jobId: string,
): Promise<KGBuildResponse> {
  return request<KGBuildResponse>(`${BASE}/kg/build/${jobId}`);
}

/** Send a natural-language query to the Q&A pipeline. */
export async function sendQuery(
  question: string,
  mode: string = 'a',
): Promise<QueryResponse> {
  return request<QueryResponse>(
    `${BASE}/query`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, mode }),
    },
    ['question', 'answer'],
  );
}

// ── Graph Visualization API ──────────────────────────────────────

/** Fetch node/edge type counts from the graph. */
export async function fetchGraphStats(): Promise<GraphStats> {
  return request<GraphStats>(`${BASE}/graph/stats`);
}

/** Fetch the full graph data (up to limit nodes). */
export async function fetchGraph(limit: number = 500): Promise<GraphData> {
  return request<GraphData>(`${BASE}/graph/full?limit=${limit}`, undefined, ['nodes', 'edges']);
}

/** Fetch neighbors of a specific node. */
export async function fetchNeighbors(
  nodeId: string,
  depth: number = 1,
): Promise<GraphData> {
  return request<GraphData>(
    `${BASE}/graph/neighbors/${encodeURIComponent(nodeId)}?depth=${depth}`,
  );
}

/** Reset (delete all nodes/edges) the Neo4j graph. */
export async function resetGraph(): Promise<GraphResetResponse> {
  return request<GraphResetResponse>(`${BASE}/graph/reset`, {
    method: 'DELETE',
  });
}
