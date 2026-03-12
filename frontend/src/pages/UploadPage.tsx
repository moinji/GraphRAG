import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { uploadDDL, generateOntology, approveVersion, startKGBuild, getKGBuildStatus, generateDDLFromNL, listDomainExamples, loadDomainExample } from '@/api/client';
import { BUILD_POLL_INTERVAL_MS } from '@/constants';
import type { ERDSchema, OntologyGenerateResponse } from '@/types/ontology';

interface UploadPageProps {
  onGenerated: (result: OntologyGenerateResponse, erd: ERDSchema) => void;
  onAutoComplete?: (result: OntologyGenerateResponse, erd: ERDSchema) => void;
}

export default function UploadPage({ onGenerated, onAutoComplete }: UploadPageProps) {
  const [file, setFile] = useState<File | null>(null);
  const [erd, setErd] = useState<ERDSchema | null>(null);
  const [includeLlm, setIncludeLlm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expandedTable, setExpandedTable] = useState<string | null>(null);
  const [autoStep, setAutoStep] = useState<string | null>(null);
  const [nlInput, setNlInput] = useState('');
  const [nlGenerating, setNlGenerating] = useState(false);
  const [generatedDDL, setGeneratedDDL] = useState<string | null>(null);
  const [examples, setExamples] = useState<{ key: string; name: string; description: string; table_count: number; fk_count: number }[]>([]);
  const [exampleLoading, setExampleLoading] = useState<string | null>(null);
  const [domain, setDomain] = useState<string>('');

  useEffect(() => {
    listDomainExamples().then(setExamples).catch(() => {});
  }, []);

  async function handleLoadExample(key: string) {
    setExampleLoading(key);
    try {
      const result = await loadDomainExample(key);
      setErd(result.erd);
      setGeneratedDDL(result.ddl);
      setExpandedTable(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load example');
    } finally {
      setExampleLoading(null);
    }
  }

  // FK lookup: target_table → source entries
  const fkBySource = new Map<string, { source_column: string; target_table: string; target_column: string }[]>();
  if (erd) {
    for (const fk of erd.foreign_keys) {
      const list = fkBySource.get(fk.source_table) ?? [];
      list.push({ source_column: fk.source_column, target_table: fk.target_table, target_column: fk.target_column });
      fkBySource.set(fk.source_table, list);
    }
  }

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    try {
      const result = await uploadDDL(file);
      setErd(result);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    if (!erd) return;
    setLoading(true);
    try {
      const result = await generateOntology(erd, !includeLlm, domain || undefined);
      onGenerated(result, erd);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleNLGenerate() {
    if (!nlInput.trim()) return;
    setNlGenerating(true);
    setGeneratedDDL(null);
    try {
      const result = await generateDDLFromNL(nlInput);
      setGeneratedDDL(result.ddl);
      if (result.erd) {
        setErd(result.erd);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'DDL generation failed');
    } finally {
      setNlGenerating(false);
    }
  }

  async function handleAutoDemo() {
    if (!file) return;
    setLoading(true);
    try {
      // 1. DDL upload
      setAutoStep('DDL 파싱 중...');
      const erdResult = await uploadDDL(file);

      // 2. Generate ontology (skip LLM for speed)
      setAutoStep('온톨로지 생성 중...');
      const genResult = await generateOntology(erdResult, true);

      // 3. Auto approve
      if (genResult.version_id) {
        setAutoStep('자동 승인 중...');
        await approveVersion(genResult.version_id);

        // 4. Start KG build
        setAutoStep('KG 빌드 시작...');
        const build = await startKGBuild(genResult.version_id, erdResult);

        // 5. Poll until complete
        setAutoStep('KG 빌드 중...');
        await new Promise<void>((resolve, reject) => {
          const poll = setInterval(async () => {
            try {
              const status = await getKGBuildStatus(build.build_job_id);
              if (status.progress?.current_step) {
                const stepMsg: Record<string, string> = {
                  data_generation: '데이터 생성 중...',
                  fk_verification: 'FK 검증 중...',
                  neo4j_load: 'Neo4j 적재 중...',
                  completed: '완료!',
                };
                setAutoStep(stepMsg[status.progress.current_step] || 'KG 빌드 중...');
              }
              if (status.status === 'succeeded') {
                clearInterval(poll);
                resolve();
              } else if (status.status === 'failed') {
                clearInterval(poll);
                reject(new Error(status.error?.message || 'Build failed'));
              }
            } catch (e) {
              clearInterval(poll);
              reject(e);
            }
          }, BUILD_POLL_INTERVAL_MS);
        });
      }

      // 6. Go directly to Q&A page
      setAutoStep('Q&A 페이지로 이동...');
      if (onAutoComplete) {
        onAutoComplete(genResult, erdResult);
      } else {
        onGenerated(genResult, erdResult);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Auto demo failed');
    } finally {
      setLoading(false);
      setAutoStep(null);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>DDL 업로드</CardTitle>
          <CardDescription>
            SQL DDL 파일을 업로드하여 스키마를 분석하고 온톨로지를 생성합니다.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ddl-file">DDL 파일 (.sql)</Label>
            <Input
              id="ddl-file"
              type="file"
              accept=".sql,.txt"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setErd(null);
                setExpandedTable(null);
              }}
            />
          </div>
          <Button onClick={handleUpload} disabled={!file || loading}>
            {loading && !erd ? '업로드 중...' : '업로드'}
          </Button>
        </CardContent>
      </Card>

      {/* Domain examples */}
      {examples.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">예제 스키마 (Demo Domains)</CardTitle>
            <CardDescription>
              4개 도메인 예제 중 하나를 선택하면 즉시 파싱됩니다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              {examples.map((ex) => (
                <button
                  key={ex.key}
                  onClick={() => handleLoadExample(ex.key)}
                  disabled={exampleLoading !== null}
                  className="rounded-lg border p-3 text-left hover:bg-accent hover:border-primary/30 transition-colors disabled:opacity-50"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-sm">{ex.name}</span>
                    {exampleLoading === ex.key && (
                      <span className="animate-spin inline-block size-3 border-2 border-current border-t-transparent rounded-full" />
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{ex.description}</p>
                  <div className="flex gap-2 mt-2">
                    <Badge variant="outline" className="text-[10px]">{ex.table_count} tables</Badge>
                    <Badge variant="outline" className="text-[10px]">{ex.fk_count} FKs</Badge>
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* NL → DDL */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">NL → DDL (자연어로 스키마 생성)</CardTitle>
          <CardDescription>
            도메인을 자연어로 설명하면 DDL을 자동 생성합니다. (LLM API 키 필요)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={nlInput}
            onChange={(e) => setNlInput(e.target.value)}
            placeholder="예: 온라인 쇼핑몰 — 고객, 상품, 주문, 리뷰, 카테고리가 있고 고객이 주문하고 상품에 리뷰를 남김"
            aria-label="도메인 설명 입력"
            rows={3}
            className="w-full rounded-lg border p-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
            disabled={nlGenerating}
          />
          <Button
            onClick={handleNLGenerate}
            disabled={!nlInput.trim() || nlGenerating}
            variant="outline"
          >
            {nlGenerating ? 'DDL 생성 중...' : 'DDL 생성'}
          </Button>
          {generatedDDL && (
            <div className="space-y-2">
              <pre className="rounded-lg border bg-muted p-3 text-xs overflow-x-auto max-h-64 overflow-y-auto">
                {generatedDDL}
              </pre>
              {erd && (
                <Badge variant="outline" className="text-xs border-green-500 text-green-600">
                  ERD 파싱 완료: {erd.tables.length} tables, {erd.foreign_keys.length} FKs
                </Badge>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {erd && (
        <>
          {/* Summary counts */}
          <Card>
            <CardHeader>
              <CardTitle>ERD 요약 (Summary)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="rounded-lg border p-3">
                  <p className="text-muted-foreground">테이블</p>
                  <p className="text-2xl font-bold">{erd.tables.length}</p>
                </div>
                <div className="rounded-lg border p-3">
                  <p className="text-muted-foreground">외래키 (FK)</p>
                  <p className="text-2xl font-bold">{erd.foreign_keys.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Tables detail */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">테이블</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>테이블명</TableHead>
                      <TableHead className="text-center">컬럼</TableHead>
                      <TableHead className="text-center">PK</TableHead>
                      <TableHead className="text-center">FKs</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {erd.tables.map((table) => {
                      const tableFks = fkBySource.get(table.name) ?? [];
                      const isExpanded = expandedTable === table.name;
                      return (
                        <TableRow
                          key={table.name}
                          tabIndex={0}
                          role="button"
                          aria-expanded={isExpanded}
                          aria-label={`${table.name} 테이블 상세`}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => setExpandedTable(isExpanded ? null : table.name)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              setExpandedTable(isExpanded ? null : table.name);
                            }
                          }}
                        >
                          <TableCell className="font-medium">{table.name}</TableCell>
                          <TableCell className="text-center">{table.columns.length}</TableCell>
                          <TableCell className="text-center">
                            <code className="text-xs">{table.primary_key ?? '-'}</code>
                          </TableCell>
                          <TableCell className="text-center">
                            {tableFks.length > 0 ? tableFks.length : '-'}
                          </TableCell>
                          <TableCell className="text-right text-muted-foreground text-xs">
                            {isExpanded ? '▲' : '▼'}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>

              {/* Expanded table detail */}
              {expandedTable && (() => {
                const table = erd.tables.find((t) => t.name === expandedTable);
                if (!table) return null;
                const tableFks = fkBySource.get(table.name) ?? [];
                const fkColumns = new Set(tableFks.map((fk) => fk.source_column));

                return (
                  <div className="mt-4 space-y-4">
                    {/* Columns */}
                    <div>
                      <h4 className="text-sm font-medium mb-2">
                        컬럼 — <code className="text-xs">{table.name}</code>
                      </h4>
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>컬럼</TableHead>
                              <TableHead>타입</TableHead>
                              <TableHead className="text-center">Nullable</TableHead>
                              <TableHead className="text-center">플래그</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {table.columns.map((col) => (
                              <TableRow key={col.name}>
                                <TableCell className="font-mono text-sm">{col.name}</TableCell>
                                <TableCell className="font-mono text-sm text-muted-foreground">
                                  {col.data_type}
                                </TableCell>
                                <TableCell className="text-center text-sm">
                                  {col.nullable ? 'YES' : 'NO'}
                                </TableCell>
                                <TableCell className="text-center">
                                  <div className="flex justify-center gap-1">
                                    {col.is_primary_key && (
                                      <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">PK</Badge>
                                    )}
                                    {fkColumns.has(col.name) && (
                                      <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">FK</Badge>
                                    )}
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    {/* FKs for this table */}
                    {tableFks.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium mb-2">외래키 (FK)</h4>
                        <div className="rounded-md border">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>컬럼</TableHead>
                                <TableHead>참조</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {tableFks.map((fk) => (
                                <TableRow key={fk.source_column}>
                                  <TableCell className="font-mono text-sm">{fk.source_column}</TableCell>
                                  <TableCell className="font-mono text-sm text-muted-foreground">
                                    {fk.target_table}.{fk.target_column}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </CardContent>
          </Card>

          {/* FK relationships overview */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">외래키 관계 (FK Relationships)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>소스</TableHead>
                      <TableHead />
                      <TableHead>타겟</TableHead>
                      <TableHead>컬럼 매핑</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {erd.foreign_keys.map((fk, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-sm">{fk.source_table}</TableCell>
                        <TableCell className="text-center text-muted-foreground">&rarr;</TableCell>
                        <TableCell className="font-mono text-sm">{fk.target_table}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {fk.source_column} &rarr; {fk.target_column}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Generate action */}
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="flex items-center gap-6">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="include-llm"
                    checked={includeLlm}
                    onCheckedChange={(checked) => setIncludeLlm(checked === true)}
                  />
                  <Label htmlFor="include-llm">LLM 보강 포함</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Label htmlFor="domain-select" className="text-sm whitespace-nowrap">도메인</Label>
                  <select
                    id="domain-select"
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    className="rounded-md border px-2 py-1 text-sm bg-background"
                  >
                    <option value="">자동 감지</option>
                    <option value="ecommerce">E-Commerce</option>
                    <option value="education">Education</option>
                    <option value="insurance">Insurance</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-3">
                <Button onClick={handleGenerate} disabled={loading} size="lg">
                  {loading && !autoStep ? '생성 중...' : '온톨로지 생성'}
                </Button>
                <Button
                  onClick={handleAutoDemo}
                  disabled={loading}
                  size="lg"
                  variant="default"
                  className="bg-amber-600 hover:bg-amber-700"
                >
                  {autoStep || 'Auto Demo (1-Click)'}
                </Button>
              </div>
              {autoStep && (
                <div className="flex items-center gap-2" role="status" aria-live="polite">
                  <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden" role="progressbar" aria-label="Auto Demo 진행률">
                    <div className="h-full bg-amber-500 rounded-full animate-pulse" style={{ width: '60%' }} />
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">{autoStep}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

    </div>
  );
}
