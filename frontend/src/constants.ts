/** Shared constants across the frontend application. */

export const DEMO_QUESTIONS = [
  { label: 'Q1', text: '고객 김민수가 주문한 상품은?' },
  { label: 'Q2', text: '김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?' },
  { label: 'Q3', text: '가장 많이 팔린 카테고리 Top 3는?' },
  { label: 'Q4', text: '김민수와 이영희가 공통으로 구매한 상품은?' },
  { label: 'Q5', text: '쿠폰 사용 주문과 미사용 주문의 평균 금액 비교' },
] as const;

export const GRAPH_DEFAULT_LIMIT = 500;
export const BUILD_POLL_INTERVAL_MS = 2000;
export const SEARCH_DEBOUNCE_MS = 300;
export const SUCCESS_MSG_TIMEOUT_MS = 5000;
