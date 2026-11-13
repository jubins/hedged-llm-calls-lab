import http from 'k6/http';
import { check } from 'k6';

const target = __ENV.TARGET || 'http://localhost:8000';
const mode = __ENV.MODE || 'hedged';

// A fixed arrival rate keeps sending requests even when responses are slow.
export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 50),
      timeUnit: '1s',
      duration: __ENV.DURATION || '3m',
      preAllocatedVUs: 50,
      maxVUs: 500,
    },
  },
  thresholds: {
    http_req_duration: ['p(99)<1000'],
    http_req_failed: ['rate<0.005'],
  },
};

export default function () {
  const res = http.post(`${target}/ask?mode=${mode}`);
  check(res, { 'status is 200': (r) => r.status === 200 });
}
