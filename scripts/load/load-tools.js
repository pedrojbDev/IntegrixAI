import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const WEBHOOK_SECRET = __ENV.WEBHOOK_SECRET || "";
const WEBHOOK_SECRET_HEADER = (__ENV.WEBHOOK_SECRET_HEADER || "x-webhook-secret").toLowerCase();
const TO_NUMBER = __ENV.TO_NUMBER || "+5511999999999";
const AGGRESSIVE_MODE = String(__ENV.AGGRESSIVE_MODE || "false").toLowerCase() === "true";
const RANDOMIZE_SEARCH_ARGS = String(__ENV.RANDOMIZE_SEARCH_ARGS || "false").toLowerCase() === "true";
const TOOLS_TARGET_VUS = Math.max(Number(__ENV.TOOLS_TARGET_VUS || 100), 1);
const SEARCH_CPF = __ENV.SEARCH_CPF || "03457351538";
const SEARCH_ESPECIALIDADE = __ENV.SEARCH_ESPECIALIDADE || "cardiologia";
const SEARCH_CIDADE = __ENV.SEARCH_CIDADE || "feira de santana";
const SEARCH_BAIRRO = __ENV.SEARCH_BAIRRO || "Centro";

const toolOkRate = new Rate("tool_ok_rate");
const upstreamSuccessRate = new Rate("upstream_success_rate");
const upstream500Rate = new Rate("upstream_500_rate");
const fallbackRate = new Rate("fallback_rate");

if (!WEBHOOK_SECRET) {
  throw new Error("WEBHOOK_SECRET is required for /tools load tests.");
}

const CIDADES = [
  "Salvador",
  "Feira de Santana",
  "Vitoria da Conquista",
  "Lauro de Freitas",
  "Jequie",
  "Ilheus",
];

const BAIRROS = [
  "Centro",
  "Pituba",
  "Brotas",
  "Barra",
  "Cabula",
  "Itapua",
];

const ESPECIALIDADES = [
  "cardiologia",
  "ortopedia",
  "clinico geral",
  "ginecologia",
  "pediatria",
  "dermatologia",
];

export const options = {
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<2000", "p(99)<3000"],
    checks: ["rate>0.99"],
    tool_ok_rate: ["rate>0.99"],
    upstream_success_rate: ["rate>0.99"],
    upstream_500_rate: ["rate<0.01"],
    fallback_rate: ["rate<0.01"],
  },
  scenarios: {
    tools_ramp: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: Math.max(Math.round(TOOLS_TARGET_VUS * 0.1), 1) },
        { duration: "2m", target: Math.max(Math.round(TOOLS_TARGET_VUS * 0.3), 1) },
        { duration: "2m", target: Math.max(Math.round(TOOLS_TARGET_VUS * 0.6), 1) },
        { duration: "3m", target: TOOLS_TARGET_VUS },
        { duration: "3m", target: TOOLS_TARGET_VUS },
        { duration: "1m", target: 0 },
      ],
      gracefulRampDown: "30s",
    },
  },
};

function randomItem(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function randomDigits(length) {
  let value = "";
  for (let index = 0; index < length; index += 1) {
    value += Math.floor(Math.random() * 10).toString();
  }
  return value;
}

function cpfCheckDigit(digits) {
  let sum = 0;
  for (let index = 0; index < digits.length; index += 1) {
    sum += Number(digits[index]) * (digits.length + 1 - index);
  }
  const remainder = (sum * 10) % 11;
  return remainder === 10 ? 0 : remainder;
}

function syntheticCpf() {
  const base = randomDigits(9);
  const firstDigit = cpfCheckDigit(base);
  const secondDigit = cpfCheckDigit(`${base}${firstDigit}`);
  return `${base}${firstDigit}${secondDigit}`;
}

function uniqueId(prefix) {
  return `${prefix}_${__VU}_${__ITER}_${Date.now()}_${randomDigits(5)}`;
}

function buildHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (WEBHOOK_SECRET) {
    headers[WEBHOOK_SECRET_HEADER] = WEBHOOK_SECRET;
  }
  return headers;
}

function searchArguments() {
  if (!RANDOMIZE_SEARCH_ARGS) {
    return {
      cpf: SEARCH_CPF,
      especialidade: SEARCH_ESPECIALIDADE,
      cidade: SEARCH_CIDADE,
      bairro: SEARCH_BAIRRO,
    };
  }

  return {
    cpf: syntheticCpf(),
    cidade: randomItem(CIDADES),
    bairro: randomItem(BAIRROS),
    especialidade: randomItem(ESPECIALIDADES),
  };
}

function buildPayload() {
  const callId = uniqueId("call");
  const toolCallId = uniqueId("tc");

  return {
    expectedToolCallId: toolCallId,
    body: {
      message: {
        type: "tool-calls",
        call: {
          id: callId,
          to: TO_NUMBER,
        },
        toolCallList: [
          {
            id: toolCallId,
            name: "search_providers",
            arguments: searchArguments(),
          },
        ],
      },
    },
  };
}

function thinkTime() {
  if (AGGRESSIVE_MODE) {
    sleep(1);
    return;
  }
  sleep(4 + Math.random() * 8);
}

export default function () {
  const payload = buildPayload();
  const response = http.post(`${BASE_URL}/tools`, JSON.stringify(payload.body), {
    headers: buildHeaders(),
    tags: {
      endpoint: "/tools",
      tool_name: "search_providers",
      mode: AGGRESSIVE_MODE ? "aggressive" : "realistic",
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
    "response has result item": () => Array.isArray(body?.results) && body.results.length > 0,
    "first result matches toolCallId": () => body?.results?.[0]?.toolCallId === payload.expectedToolCallId,
    "first result is search_providers": () => body?.results?.[0]?.result?.tool_name === "search_providers",
    "first result has boolean ok": () => typeof body?.results?.[0]?.result?.ok === "boolean",
  });

  const result = body?.results?.[0]?.result;
  const errorCode = result?.error?.code || "none";
  const finalState = result?.final_state || "unknown";
  const isUpstream500 = errorCode === "UPSTREAM_503";
  const isFallback = finalState === "TRANSFERIDA_HUMANO";
  const isUpstreamSuccess = result?.ok === true && !isFallback;

  toolOkRate.add(result?.ok === true, {
    error_code: errorCode,
    final_state: finalState,
  });
  upstreamSuccessRate.add(isUpstreamSuccess, {
    error_code: errorCode,
    final_state: finalState,
  });
  upstream500Rate.add(isUpstream500, {
    error_code: errorCode,
    final_state: finalState,
  });
  fallbackRate.add(isFallback, {
    error_code: errorCode,
    final_state: finalState,
  });

  thinkTime();
}
