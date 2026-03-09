import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { sendQuery, sendWisdomQuery } from '@/api/client';
import { streamQuery } from '@/api/sse';
import { DEMO_QUESTIONS, DEMO_QUESTIONS_EN, WISDOM_DEMO_QUESTIONS } from '@/constants';
import DIKWTimeline from '@/components/wisdom/DIKWTimeline';
import type { ChatMessage, QueryResponse } from '@/types/ontology';

type Mode = 'a' | 'b' | 'w';

interface QueryPageProps {
  onBack: () => void;
}

export default function QueryPage({ onBack }: QueryPageProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [mode, setMode] = useState<Mode>('a');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const abortRef = useRef<AbortController | null>(null);

  async function handleSend(question: string) {
    if (!question.trim() || sending) return;

    const userMsg: ChatMessage = { role: 'user', content: question };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);

    try {
      if (mode === 'w') {
        const wisdomData = await sendWisdomQuery(question);
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: wisdomData.summary || 'DIKW 분석이 완료되었습니다.',
          wisdomData,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setSending(false);
      } else if (mode === 'b') {
        // SSE streaming for mode B
        const placeholder: ChatMessage = { role: 'assistant', content: '', streaming: true };
        setMessages((prev) => [...prev, placeholder]);

        abortRef.current = streamQuery(question, mode, {
          onMetadata: (meta) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, data: meta as QueryResponse };
              return updated;
            });
          },
          onToken: (token) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, content: last.content + token };
              return updated;
            });
          },
          onComplete: (data) => {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: 'assistant',
                content: data.answer,
                data,
                streaming: false,
              };
              return updated;
            });
            setSending(false);
            abortRef.current = null;
          },
          onError: (error) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.streaming) {
                updated[updated.length - 1] = {
                  role: 'assistant',
                  content: last.content || error.message,
                  streaming: false,
                };
              } else {
                updated.push({ role: 'assistant', content: error.message });
              }
              return updated;
            });
            setSending(false);
            abortRef.current = null;
          },
        });
      } else {
        // Mode A: regular fetch
        const data = await sendQuery(question, mode);
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: data.answer,
          data,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setSending(false);
      }
    } catch (e) {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: e instanceof Error ? e.message : 'Query failed',
      };
      setMessages((prev) => [...prev, errorMsg]);
      setSending(false);
    }
  }

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  const demoQuestions = mode === 'w' ? WISDOM_DEMO_QUESTIONS : DEMO_QUESTIONS;
  const demoQuestionsEn = mode === 'w' ? null : DEMO_QUESTIONS_EN;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">
          {mode === 'w' ? 'DIKW 인사이트 분석' : '지식 그래프 Q&A'}
        </h2>
        <div className="flex items-center gap-3">
          {/* A/B/W Mode Toggle */}
          <div className="flex items-center gap-1 rounded-lg border p-1" role="radiogroup" aria-label="질의 모드 선택">
            <button
              onClick={() => setMode('a')}
              role="radio"
              aria-checked={mode === 'a'}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                mode === 'a'
                  ? 'bg-blue-600 text-white'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              A 템플릿
            </button>
            <button
              onClick={() => setMode('b')}
              role="radio"
              aria-checked={mode === 'b'}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                mode === 'b'
                  ? 'bg-orange-600 text-white'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              B 로컬
            </button>
            <button
              onClick={() => setMode('w')}
              role="radio"
              aria-checked={mode === 'w'}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                mode === 'w'
                  ? 'bg-amber-600 text-white'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              W 위즈덤
            </button>
          </div>
          <button
            onClick={onBack}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; 리뷰로 돌아가기
          </button>
        </div>
      </div>

      {/* Demo question buttons */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-4">
        {demoQuestions.map((q, i) => (
          <button
            key={`${mode}-${i}`}
            onClick={() => handleSend(q.text)}
            disabled={sending}
            className={`text-left text-sm rounded-lg border p-2 hover:bg-muted transition-colors disabled:opacity-50 ${
              mode === 'w' ? 'border-amber-200 hover:border-amber-400' : ''
            }`}
          >
            <span
              className={`inline-block mr-1.5 px-1.5 py-0.5 rounded text-xs font-semibold ${
                mode === 'w'
                  ? 'bg-amber-500 text-white'
                  : 'bg-primary text-primary-foreground'
              }`}
            >
              {q.label}
            </span>
            {q.text}
          </button>
        ))}
        {demoQuestionsEn?.map((q, i) => (
          <button
            key={`${mode}-en-${i}`}
            onClick={() => handleSend(q.text)}
            disabled={sending}
            className="text-left text-sm rounded-lg border border-emerald-200 p-2 hover:bg-muted hover:border-emerald-400 transition-colors disabled:opacity-50"
          >
            <span className="inline-block mr-1.5 px-1.5 py-0.5 rounded text-xs font-semibold bg-emerald-600 text-white">
              {q.label}
              <span className="ml-0.5 text-[10px] opacity-80">EN</span>
            </span>
            {q.text}
          </button>
        ))}
      </div>

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-4" role="log" aria-live="polite" aria-label="채팅 메시지">
        {messages.length === 0 && (
          <p className="text-center text-muted-foreground mt-8">
            {mode === 'w'
              ? 'Wisdom 데모 질문을 클릭하여 DIKW 분석을 시작하세요.'
              : '위 데모 질문을 클릭하거나 아래에 직접 질문을 입력하세요.'}
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`rounded-lg p-3 text-sm ${
                msg.role === 'user'
                  ? 'max-w-[80%] bg-primary text-primary-foreground'
                  : msg.wisdomData
                    ? 'max-w-[90%] bg-muted'
                    : 'max-w-[80%] bg-muted'
              }`}
            >
              {msg.wisdomData ? (
                <DIKWTimeline
                  data={msg.wisdomData}
                  onRelatedQuery={(q) => handleSend(q)}
                />
              ) : (
                <>
                  <p className="whitespace-pre-wrap">
                    {msg.content}
                    {msg.streaming && <span className="inline-block w-2 h-4 bg-current animate-pulse ml-0.5 align-text-bottom" />}
                  </p>
                  {msg.data && !msg.streaming && <AssistantDetail data={msg.data} />}
                </>
              )}
            </div>
          </div>
        ))}
        {sending && !messages.some(m => m.streaming) && (
          <div className="flex justify-start" role="status" aria-label="답변 생성 중">
            <div className={`rounded-lg p-3 text-sm text-muted-foreground animate-pulse ${
              mode === 'w' ? 'bg-amber-50 border border-amber-200' : 'bg-muted'
            }`}>
              {mode === 'w' ? 'DIKW 분석 중... (다중 쿼리 수집 + LLM 분석)' : '답변 생성 중...'}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend(input);
            }
          }}
          placeholder={
            mode === 'w'
              ? '패턴, 추천, What-If 등 인사이트 질문을 입력하세요...'
              : '질문을 입력하세요...'
          }
          aria-label="질문 입력"
          rows={2}
          className="flex-1 rounded-lg border p-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
          disabled={sending}
        />
        <Button
          onClick={() => handleSend(input)}
          disabled={!input.trim() || sending}
          className="self-end"
        >
          {sending ? '...' : '전송'}
        </Button>
      </div>
    </div>
  );
}

function AssistantDetail({ data }: { data: QueryResponse }) {
  const [showCypher, setShowCypher] = useState(false);
  const [showPaths, setShowPaths] = useState(false);
  const [showSubgraph, setShowSubgraph] = useState(false);

  return (
    <div className="mt-2 space-y-2">
      {/* Badges */}
      <div className="flex gap-1 flex-wrap">
        {/* Mode badge */}
        <Badge
          variant="outline"
          className={`text-xs ${
            data.mode === 'b'
              ? 'border-orange-500 text-orange-600'
              : 'border-blue-500 text-blue-600'
          }`}
        >
          {data.mode === 'b' ? 'B 로컬' : 'A 템플릿'}
        </Badge>
        {data.template_id && (
          <Badge variant="secondary" className="text-xs">
            {data.template_id}
          </Badge>
        )}
        {data.route && (
          <Badge variant="outline" className="text-xs">
            {data.route}
          </Badge>
        )}
        {data.matched_by && (
          <Badge
            variant={data.matched_by === 'rule' ? 'default' : 'secondary'}
            className="text-xs"
          >
            {data.matched_by}
          </Badge>
        )}
        {data.cached && (
          <Badge variant="outline" className="text-xs border-green-500 text-green-600">
            cached
          </Badge>
        )}
      </div>

      {/* Latency + tokens (B) */}
      {(data.latency_ms != null || data.llm_tokens_used != null) && (
        <div className="flex gap-2 text-xs text-muted-foreground">
          {data.latency_ms != null && <span>{data.latency_ms}ms</span>}
          {data.llm_tokens_used != null && (
            <span>{data.llm_tokens_used} tokens</span>
          )}
        </div>
      )}

      {/* Cypher collapsible */}
      {data.cypher && (
        <div>
          <button
            onClick={() => setShowCypher(!showCypher)}
            aria-expanded={showCypher}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {showCypher ? '▼ Cypher (쿼리)' : '▶ Cypher (쿼리)'}
          </button>
          {showCypher && (
            <pre className="mt-1 rounded bg-background p-2 text-xs overflow-x-auto border">
              {data.cypher}
            </pre>
          )}
        </div>
      )}

      {/* Subgraph context collapsible (B) */}
      {data.subgraph_context && (
        <div>
          <button
            onClick={() => setShowSubgraph(!showSubgraph)}
            aria-expanded={showSubgraph}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {showSubgraph ? '▼' : '▶'} 서브그래프 컨텍스트
          </button>
          {showSubgraph && (
            <pre className="mt-1 rounded bg-background p-2 text-xs overflow-x-auto border whitespace-pre-wrap">
              {data.subgraph_context}
            </pre>
          )}
        </div>
      )}

      {/* Paths collapsible */}
      {data.paths.length > 0 && (
        <div>
          <button
            onClick={() => setShowPaths(!showPaths)}
            aria-expanded={showPaths}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {showPaths ? '▼' : '▶'} 근거 경로 ({data.paths.length})
          </button>
          {showPaths && (
            <ul className="mt-1 space-y-1 text-xs">
              {data.paths.map((p, i) => (
                <li key={i} className="rounded bg-background p-1 border font-mono">
                  {p}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Error */}
      {data.error && (
        <p className="text-xs text-destructive" role="alert">{data.error}</p>
      )}
    </div>
  );
}
