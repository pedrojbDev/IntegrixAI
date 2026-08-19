import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const WEBHOOK_SECRET = __ENV.WEBHOOK_SECRET || "";
const WEBHOOK_SECRET_HEADER = (__ENV.WEBHOOK_SECRET_HEADER || "x-webhook-secret").toLowerCase();
const TO_NUMBER = __ENV.TO_NUMBER || "+5511999999999";
const SEARCH_CPF = __ENV.SEARCH_CPF || "03457351538";
const SEARCH_ESPECIALIDADE = __ENV.SEARCH_ESPECIALIDADE || "cardiologia";
const SEARCH_CIDADE = __ENV.SEARCH_CIDADE || "feira de santana";

const toolOkRate = new Rate("tool_ok_rate");

if (!WEBHOOK_SECRET) {
  throw new Error("WEBHOOK_SECRET is required for /tools idempotency load tests.");
}

export const options = {
  vus: 20,
  duration: "1m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000"],
    checks: ["rate>0.99"],
    tool_ok_rate: ["rate>0.99"],
  },
};

function buildHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (WEBHOOK_SECRET) {
    headers[WEBHOOK_SECRET_HEADER] = WEBHOOK_SECRET;
  }
  return headers;
}

function payloadForVu() {
  const toolCallId = `idem-tool-vu-${__VU}`;
  return {
    expectedToolCallId: toolCallId,
    body: {
      message: {
        type: "tool-calls",
        call: {
          id: `idem-call-vu-${__VU}`,
          to: TO_NUMBER,
        },
        toolCallList: [
          {
            id: toolCallId,
            name: "search_providers",
            arguments: {
              cpf: SEARCH_CPF,
              especialidade: SEARCH_ESPECIALIDADE,
              cidade: SEARCH_CIDADE,
            },
          },
        ],
      },
    },
  };
}

export default function () {
  const payload = payloadForVu();
  const response = http.post(`${BASE_URL}/tools`, JSON.stringify(payload.body), {
    headers: buildHeaders(),
    tags: {
      endpoint: "/tools",
      test_type: "idempotency",
      tool_name: "search_providers",
    },
  });

  let body = null;
  try {
    body = response.json();
  } catch (_error) {
    body = null;
  }

  check(response, {
    "status is 200": (res) => res.status === 200,
    "response has results": () => Array.isArray(body?.results) && body.results.length > 0,
    "result matches toolCallId": () => body?.results?.[0]?.toolCallId === payload.expectedToolCallId,
    "result is search_providers": () => body?.results?.[0]?.result?.tool_name === "search_providers",
    "result has boolean ok": () => typeof body?.results?.[0]?.result?.ok === "boolean",
  });

  const result = body?.results?.[0]?.result;
  toolOkRate.add(result?.ok === true, {
    error_code: result?.error?.code || "none",
    final_state: result?.final_state || "unknown",
  });

  sleep(1);
}
