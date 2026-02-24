import type {
  ERDSchema,
  OntologyApproveResponse,
  OntologyGenerateResponse,
  OntologySpec,
  OntologyUpdateResponse,
  OntologyVersionResponse,
} from '@/types/ontology';

const BASE = '/api/v1';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(body.detail ?? `HTTP ${resp.status}`);
  }
  return resp.json() as Promise<T>;
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
  return request<OntologyGenerateResponse>(`${BASE}/ontology/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ erd, skip_llm: skipLlm }),
  });
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
