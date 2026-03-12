/**
 * Tests for shared constants.
 */
import { describe, it, expect } from 'vitest';
import {
  DEMO_QUESTIONS,
  DEMO_QUESTIONS_EN,
  DEMO_QUESTIONS_C,
  WISDOM_DEMO_QUESTIONS,
  GRAPH_DEFAULT_LIMIT,
  BUILD_POLL_INTERVAL_MS,
  SSE_STREAM_TIMEOUT_MS,
} from '@/constants';

describe('DEMO_QUESTIONS', () => {
  it('has 5 Korean demo questions', () => {
    expect(DEMO_QUESTIONS).toHaveLength(5);
  });

  it('each has label and text', () => {
    for (const q of DEMO_QUESTIONS) {
      expect(q.label).toBeTruthy();
      expect(q.text).toBeTruthy();
    }
  });

  it('labels are Q1-Q5', () => {
    const labels = DEMO_QUESTIONS.map((q) => q.label);
    expect(labels).toEqual(['Q1', 'Q2', 'Q3', 'Q4', 'Q5']);
  });
});

describe('DEMO_QUESTIONS_EN', () => {
  it('has English demo questions', () => {
    expect(DEMO_QUESTIONS_EN.length).toBeGreaterThan(0);
  });
});

describe('DEMO_QUESTIONS_C', () => {
  it('has 5 hybrid mode questions', () => {
    expect(DEMO_QUESTIONS_C).toHaveLength(5);
  });

  it('labels start with C', () => {
    for (const q of DEMO_QUESTIONS_C) {
      expect(q.label).toMatch(/^C\d/);
    }
  });
});

describe('WISDOM_DEMO_QUESTIONS', () => {
  it('has 5 wisdom questions', () => {
    expect(WISDOM_DEMO_QUESTIONS).toHaveLength(5);
  });

  it('labels start with W', () => {
    for (const q of WISDOM_DEMO_QUESTIONS) {
      expect(q.label).toMatch(/^W\d/);
    }
  });
});

describe('Config constants', () => {
  it('GRAPH_DEFAULT_LIMIT is reasonable', () => {
    expect(GRAPH_DEFAULT_LIMIT).toBe(500);
  });

  it('BUILD_POLL_INTERVAL_MS is 2s', () => {
    expect(BUILD_POLL_INTERVAL_MS).toBe(2000);
  });

  it('SSE_STREAM_TIMEOUT_MS is 2 minutes', () => {
    expect(SSE_STREAM_TIMEOUT_MS).toBe(120_000);
  });
});
