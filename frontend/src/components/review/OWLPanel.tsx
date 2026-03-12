import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { exportOWL, validateSHACL } from '@/api/client';
import type { OWLExportResponse, SHACLValidationResponse } from '@/types/ontology';

interface OWLPanelProps {
  versionId: number | null;
  locked: boolean;
}

export default function OWLPanel({ versionId, locked }: OWLPanelProps) {
  const [format, setFormat] = useState<string>('turtle');
  const [owlData, setOwlData] = useState<OWLExportResponse | null>(null);
  const [owlLoading, setOwlLoading] = useState(false);

  const [shaclData, setShaclData] = useState<SHACLValidationResponse | null>(null);
  const [shaclLoading, setShaclLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  if (!locked) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          온톨로지를 승인한 후 OWL/SHACL 기능을 사용할 수 있습니다.
        </CardContent>
      </Card>
    );
  }

  async function handleExport() {
    if (!versionId) return;
    setOwlLoading(true);
    setError(null);
    try {
      const resp = await exportOWL(versionId, format);
      setOwlData(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'OWL export failed');
    } finally {
      setOwlLoading(false);
    }
  }

  async function handleValidate() {
    if (!versionId) return;
    setShaclLoading(true);
    setError(null);
    try {
      const resp = await validateSHACL(versionId);
      setShaclData(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'SHACL validation failed');
    } finally {
      setShaclLoading(false);
    }
  }

  function handleDownload() {
    if (!owlData) return;
    const ext = format === 'turtle' ? 'ttl' : format === 'xml' ? 'rdf' : 'jsonld';
    const mime = format === 'turtle' ? 'text/turtle' : format === 'xml' ? 'application/rdf+xml' : 'application/ld+json';
    const blob = new Blob([owlData.content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ontology_v${versionId}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* OWL Export */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">OWL Export</CardTitle>
            <div className="flex items-center gap-2">
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value)}
                className="rounded border bg-background px-2 py-1 text-sm"
              >
                <option value="turtle">Turtle</option>
                <option value="xml">RDF/XML</option>
                <option value="json-ld">JSON-LD</option>
              </select>
              <Button onClick={handleExport} disabled={owlLoading} size="sm" variant="outline">
                {owlLoading ? 'Exporting...' : 'Export'}
              </Button>
              {owlData && (
                <Button onClick={handleDownload} size="sm" variant="ghost">
                  Download
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {owlData ? (
            <>
              <div className="mb-3 flex gap-2">
                <Badge variant="outline">{owlData.triple_count} triples</Badge>
                <Badge variant="outline">{owlData.class_count} classes</Badge>
                <Badge variant="outline">{owlData.property_count} properties</Badge>
              </div>
              <pre className="rounded-lg border bg-muted p-3 text-xs overflow-x-auto max-h-96 overflow-y-auto font-mono">
                {owlData.content}
              </pre>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Export 버튼을 클릭하면 온톨로지를 OWL 형식으로 변환합니다.
            </p>
          )}
        </CardContent>
      </Card>

      {/* SHACL Validation */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">SHACL Validation</CardTitle>
            <div className="flex items-center gap-2">
              {shaclData && (
                <Badge variant={shaclData.conforms ? 'default' : 'destructive'}>
                  {shaclData.conforms ? 'PASS' : 'FAIL'}
                </Badge>
              )}
              <Button onClick={handleValidate} disabled={shaclLoading} size="sm" variant="outline">
                {shaclLoading ? 'Validating...' : 'Validate'}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {shaclData ? (
            shaclData.conforms ? (
              <div className="rounded-lg border border-green-500 bg-green-50 p-3 text-sm text-green-800">
                TBox 스키마 검증 통과 — 모든 Shape 제약 충족
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  {shaclData.issue_count}개 이슈 발견 (Level: {shaclData.level})
                </p>
                {shaclData.issues.map((issue, i) => (
                  <div
                    key={i}
                    className={`rounded-lg border p-2 text-xs ${
                      issue.severity === 'error'
                        ? 'border-red-400 bg-red-50 text-red-800'
                        : 'border-amber-400 bg-amber-50 text-amber-800'
                    }`}
                  >
                    <span className="font-medium">[{issue.severity}]</span> {issue.message}
                  </div>
                ))}
              </div>
            )
          ) : (
            <p className="text-sm text-muted-foreground">
              Validate 버튼을 클릭하면 SHACL Shape 기반 스키마 검증을 수행합니다.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
