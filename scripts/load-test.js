/**
 * k6 load test script for GraphRAG API.
 *
 * Usage:
 *   k6 run scripts/load-test.js
 *   k6 run --vus 10 --duration 30s scripts/load-test.js
 *   K6_BASE_URL=http://localhost:8000 k6 run scripts/load-test.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const queryLatency = new Trend('query_latency', true);

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || '';

export const options = {
  stages: [
    { duration: '10s', target: 5 },   // ramp up
    { duration: '30s', target: 10 },   // hold
    { duration: '10s', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95th percentile < 2s
    errors: ['rate<0.1'],               // error rate < 10%
  },
};

const headers = {
  'Content-Type': 'application/json',
  ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
};

const DEMO_QUESTIONS = [
  '고객 김민수가 주문한 상품은?',
  '가장 많이 팔린 카테고리 Top 3는?',
  'List all products in Electronics category',
  '김민수와 이영희가 공통으로 구매한 상품은?',
  '쿠폰 사용 주문과 미사용 주문의 평균 금액 비교',
];

export default function () {
  // 1. Health check
  const healthRes = http.get(`${BASE_URL}/api/v1/health`);
  check(healthRes, {
    'health status 200': (r) => r.status === 200,
  });
  errorRate.add(healthRes.status !== 200);

  // 2. Query (cached Mode A — fast path)
  const question = DEMO_QUESTIONS[Math.floor(Math.random() * DEMO_QUESTIONS.length)];
  const queryRes = http.post(
    `${BASE_URL}/api/v1/query`,
    JSON.stringify({ question, mode: 'a' }),
    { headers },
  );
  check(queryRes, {
    'query status 200': (r) => r.status === 200,
    'query has answer': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.answer && body.answer.length > 0;
      } catch {
        return false;
      }
    },
  });
  errorRate.add(queryRes.status !== 200);
  queryLatency.add(queryRes.timings.duration);

  sleep(0.5 + Math.random());
}

export function handleSummary(data) {
  const p95 = data.metrics.http_req_duration?.values?.['p(95)'] || 0;
  const errRate = data.metrics.errors?.values?.rate || 0;
  const totalReqs = data.metrics.http_reqs?.values?.count || 0;

  console.log('\n=== GraphRAG Load Test Summary ===');
  console.log(`Total requests: ${totalReqs}`);
  console.log(`p95 latency: ${p95.toFixed(0)}ms`);
  console.log(`Error rate: ${(errRate * 100).toFixed(1)}%`);
  console.log(`Query p95: ${(data.metrics.query_latency?.values?.['p(95)'] || 0).toFixed(0)}ms`);
  console.log('================================\n');

  return {};
}
