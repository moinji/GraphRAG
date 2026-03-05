import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { sendQuery } from '@/api/client';
import { DEMO_QUESTIONS } from '@/constants';
import type { ChatMessage, QueryResponse } from '@/types/ontology';

interface QueryPageProps {
  onBack: () => void;
}

export default function QueryPage({ onBack }: QueryPageProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [mode, setMode] = useState<'a' | 'b'>('a');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend(question: string) {
    if (!question.trim() || sending) return;

    const userMsg: ChatMessage = { role: 'user', content: question };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);

    try {
      const data = await sendQuery(question, mode);
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: data.answer,
        data,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e) {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: e instanceof Error ? e.message : 'Query failed',
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">지식 그래프 Q&A</h2>
        <div className="flex items-center gap-3">
          {/* A/B Mode Toggle */}
          <div className="flex items-center gap-1 rounded-lg border p-1">
            <button
              onClick={() => setMode('a')}
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
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                mode === 'b'
                  ? 'bg-orange-600 text-white'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              B 로컬
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
        {DEMO_QUESTIONS.map((q, i) => (
          <button
            key={i}
            onClick={() => handleSend(q.text)}
            disabled={sending}
            className="text-left text-sm rounded-lg border p-2 hover:bg-muted transition-colors disabled:opacity-50"
          >
            <span className="inline-block mr-1.5 px-1.5 py-0.5 rounded bg-primary text-primary-foreground text-xs font-semibold">
              {q.label}
            </span>
            {q.text}
          </button>
        ))}
      </div>

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-4">
        {messages.length === 0 && (
          <p className="text-center text-muted-foreground mt-8">
            위 데모 질문을 클릭하거나 아래에 직접 질문을 입력하세요.
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg p-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.data && <AssistantDetail data={msg.data} />}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-lg p-3 text-sm text-muted-foreground animate-pulse">
              답변 생성 중...
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
          placeholder="질문을 입력하세요..."
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

      {/* Latency + tokens (B안) */}
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

      {/* Subgraph context collapsible (B안) */}
      {data.subgraph_context && (
        <div>
          <button
            onClick={() => setShowSubgraph(!showSubgraph)}
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
        <p className="text-xs text-destructive">{data.error}</p>
      )}
    </div>
  );
}
