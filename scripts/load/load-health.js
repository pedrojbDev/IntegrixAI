import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export const options = {
  vus: 50,
  duration: "1m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const response = http.get(`${BASE_URL}/health`, {
    tags: {
      endpoint: "/health",
      test_type: "sanity",
    },
  });

  check(response, {
    "status is 200": (res) => res.status === 200,
    "body contains status ok": (res) => res.body.includes('"status":"ok"'),
  });

  sleep(1);
}
