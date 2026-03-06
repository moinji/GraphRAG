/** Shared constants across the frontend application. */

export const DEMO_QUESTIONS = [
  { label: 'Q1', text: '고객 김민수가 주문한 상품은?' },
  { label: 'Q2', text: '김민수가 주문한 상품과 같은 카테고리에서 리뷰 평점 Top 3 상품은?' },
  { label: 'Q3', text: '가장 많이 팔린 카테고리 Top 3는?' },
  { label: 'Q4', text: '김민수와 이영희가 공통으로 구매한 상품은?' },
  { label: 'Q5', text: '쿠폰 사용 주문과 미사용 주문의 평균 금액 비교' },
] as const;

export const DEMO_QUESTIONS_EN = [
  { label: 'Q1', text: 'What products did 김민수 order?' },
  { label: 'Q3', text: 'Top 3 best-selling categories?' },
  { label: 'Q5', text: 'Coupon used vs unused average amount comparison' },
] as const;

export const WISDOM_DEMO_QUESTIONS = [
  { label: 'W1', text: '고객 구매 패턴에서 어떤 트렌드가 보이나요?' },
  { label: 'W2', text: '리뷰 평점이 높은 상품이 실제로 더 많이 팔리나요?' },
  { label: 'W3', text: '김민수에게 어떤 상품을 추천하면 좋을까요?' },
  { label: 'W4', text: '애플코리아 공급이 중단되면 어떤 영향이 있나요?' },
  { label: 'W5', text: '김민수에 대한 DIKW 종합 분석을 해줘' },
] as const;

export const GRAPH_DEFAULT_LIMIT = 500;
export const BUILD_POLL_INTERVAL_MS = 2000;
export const SEARCH_DEBOUNCE_MS = 300;
export const SUCCESS_MSG_TIMEOUT_MS = 5000;
