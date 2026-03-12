/**
 * Tests for API client (client.ts).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { APIError, setApiKey, getApiKey } from '@/api/client';

describe('APIError', () => {
  it('stores detail as message', () => {
    const err = new APIError('Something went wrong');
    expect(err.message).toBe('Something went wrong');
    expect(err.name).toBe('APIError');
    expect(err.errors).toEqual([]);
  });

  it('stores errors array', () => {
    const err = new APIError('fail', ['err1', 'err2']);
    expect(err.errors).toEqual(['err1', 'err2']);
  });

  it('is instanceof Error', () => {
    const err = new APIError('test');
    expect(err).toBeInstanceOf(Error);
  });
});

describe('API key management', () => {
  afterEach(() => setApiKey(null));

  it('defaults to null', () => {
    setApiKey(null);
    expect(getApiKey()).toBeNull();
  });

  it('stores and retrieves key', () => {
    setApiKey('test-key-123');
    expect(getApiKey()).toBe('test-key-123');
  });

  it('clears key with null', () => {
    setApiKey('key');
    setApiKey(null);
    expect(getApiKey()).toBeNull();
  });
});

describe('sendQuery', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends POST with question and mode', async () => {
    const mockResponse = {
      ok: true,
      json: () => Promise.resolve({
        question: 'test?',
        answer: 'answer',
        cypher: '',
        paths: [],
        template_id: '',
        route: 'unsupported',
        matched_by: 'none',
        mode: 'a',
      }),
    };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const { sendQuery } = await import('@/api/client');
    const result = await sendQuery('test?', 'a');

    expect(result.question).toBe('test?');
    expect(result.answer).toBe('answer');

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[0]).toBe('/api/v1/query');
    const body = JSON.parse(fetchCall[1].body);
    expect(body.question).toBe('test?');
    expect(body.mode).toBe('a');
  });

  it('throws APIError on non-ok response', async () => {
    const mockResponse = {
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: () => Promise.resolve({ detail: 'Invalid question' }),
    };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const { sendQuery } = await import('@/api/client');
    await expect(sendQuery('', 'a')).rejects.toThrow('Invalid question');
  });
});
