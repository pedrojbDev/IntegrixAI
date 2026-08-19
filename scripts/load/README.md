# Load Testing for IntegrixAI

`/tools` is the critical endpoint in this backend because it is the entry point for Vapi tool-calls during live voice calls. In production, each simultaneous call can generate tool execution pressure on tenant resolution, webhook authorization, idempotency, audit writing, metrics, database access, and the PB Saude external API integration.

This directory adds a reproducible `k6` setup focused on validating whether the backend can sustain roughly 100 simultaneous Vapi-driven calls without unacceptable latency or error rate.

## Files

- `load-health.js`
  - Baseline sanity check for `GET /health`.
  - Uses 50 VUs for 1 minute.
  - This is not the main production test.
- `load-tools.js`
  - Main load scenario for `POST /tools`.
  - Sends a Vapi-compatible `search_providers` payload for the active `pbsaude` implementation.
  - Uses a staged ramp up to 100 VUs, then sustains 100 VUs.
  - Randomizes `message.call.id` and `message.toolCallList[0].id`.
  - Uses a known functional `search_providers` body by default: `cpf=03457351538`, `especialidade=cardiologia`, `cidade=feira de santana`, `bairro=Centro`.
  - Can randomize `cpf`, `cidade`, `bairro`, and `especialidade` with `RANDOMIZE_SEARCH_ARGS=true`, but that mode should only be used when the target environment accepts synthetic data.
  - Sends `x-webhook-secret` by default, or the header configured with `WEBHOOK_SECRET_HEADER`.
  - Validates that `/tools` returned a result for the expected tool call and that the result is for `search_providers`.
- `load-idempotency.js`
  - Sends the same `call_id` + `tool_call_id` repeatedly per virtual user.
  - Designed to trigger idempotency hits when `DB_ENABLED=true`.
  - Useful to confirm duplicate deliveries stay stable under load.
- `run-load-tests.ps1`
  - PowerShell helper for Windows.
- `run-load-tests.sh`
  - Bash helper for Linux and macOS.
- `.env.load.example`
  - Example environment values for the load tools.

## Why `/tools` matters

Vapi voice calls hit `POST /tools` when the assistant needs backend actions. For IntegrixAI, that endpoint is where these concerns converge:

- Vapi webhook authorization
- tenant resolution from `message.call.to`
- tool dispatch
- PB Saude `search_providers` execution
- idempotency lookup and persistence
- audit event writes
- metrics collection
- database pressure
- upstream external API latency

If `/tools` degrades, the live assistant degrades with it.

## Prerequisites

- A running IntegrixAI deployment reachable through `BASE_URL`
- A valid `WEBHOOK_SECRET`
- A DID in `TO_NUMBER` that is mapped in `TENANT_MAP` for the active tenant
- `k6` installed locally

Before running load tests, run [`smoke_local.py`](../smoke_local.py) first when testing a local or freshly deployed environment.

## Install k6

### Windows

PowerShell:

```powershell
winget install k6
```

### Linux

Use the package instructions for your distribution from the official k6 docs. On Debian/Ubuntu-like systems, prefer the official Grafana k6 package steps:

```bash
sudo apt-get update
sudo apt-get install -y gnupg ca-certificates
```

If `k6` is still missing, see the official install guide: [Install k6](https://grafana.com/docs/k6/latest/set-up/install-k6/)

## Environment

Copy the sample and fill in safe values:

```bash
cp scripts/load/.env.load.example scripts/load/.env.load
```

Important:

- Do not commit real secrets.
- `TO_NUMBER` should be a DID that resolves to the active tenant in the target environment.

Example values:

```env
BASE_URL=https://api.example.com
WEBHOOK_SECRET=replace-me
WEBHOOK_SECRET_HEADER=x-webhook-secret
AGGRESSIVE_MODE=false
RANDOMIZE_SEARCH_ARGS=false
TO_NUMBER=+5511999999999
SEARCH_CPF=03457351538
SEARCH_ESPECIALIDADE=cardiologia
SEARCH_CIDADE=feira de santana
SEARCH_BAIRRO=Centro
```

## How to run

Recommended progression:

1. Run `health`
2. Run a small `tools` test locally or against staging
3. Run the full `tools` ramp
4. Run `idempotency`
5. Only then consider production

Do not run aggressive tests against production during peak hours.
Prefer staging before production.

### PowerShell

Health only:

```powershell
.\scripts\load\run-load-tests.ps1 -BaseUrl http://127.0.0.1:8000 -Mode health
```

Main `/tools` test in realistic mode:

```powershell
.\scripts\load\run-load-tests.ps1 -BaseUrl http://127.0.0.1:8000 -Mode tools -ToNumber +5511999999999
```

Main `/tools` test in aggressive mode:

```powershell
.\scripts\load\run-load-tests.ps1 -BaseUrl http://127.0.0.1:8000 -Mode tools -ToNumber +5511999999999 -AggressiveMode
```

Idempotency test:

```powershell
.\scripts\load\run-load-tests.ps1 -BaseUrl http://127.0.0.1:8000 -Mode idempotency -ToNumber +5511999999999
```

Run all:

```powershell
.\scripts\load\run-load-tests.ps1 -BaseUrl https://api.example.com -WebhookSecret replace-me -Mode all -ToNumber +5511999999999
```

On Windows, the helper reads `WEBHOOK_SECRET` and `WEBHOOK_SECRET_HEADER` from the repo `.env` when you do not pass them explicitly.

Override the `search_providers` body when needed:

```powershell
.\scripts\load\run-load-tests.ps1 -BaseUrl http://127.0.0.1:8000 -Mode tools -ToNumber +5511999999999 -SearchCpf 03457351538 -SearchEspecialidade cardiologia -SearchCidade "feira de santana" -SearchBairro Centro
```

### Bash

Health only:

```bash
./scripts/load/run-load-tests.sh --base-url http://127.0.0.1:8000 --mode health
```

Main `/tools` test in realistic mode:

```bash
./scripts/load/run-load-tests.sh --base-url http://127.0.0.1:8000 --mode tools --to-number +5511999999999
```

Main `/tools` test in aggressive mode:

```bash
./scripts/load/run-load-tests.sh --base-url http://127.0.0.1:8000 --mode tools --to-number +5511999999999 --aggressive
```

Idempotency test:

```bash
./scripts/load/run-load-tests.sh --base-url http://127.0.0.1:8000 --mode idempotency --to-number +5511999999999
```

Run all:

```bash
./scripts/load/run-load-tests.sh --base-url https://api.example.com --webhook-secret replace-me --mode all --to-number +5511999999999
```

On Linux/macOS, the helper also reads `WEBHOOK_SECRET` and `WEBHOOK_SECRET_HEADER` from the repo `.env` when they are not passed explicitly.

Override the `search_providers` body when needed:

```bash
./scripts/load/run-load-tests.sh --base-url http://127.0.0.1:8000 --mode tools --to-number +5511999999999 --search-cpf 03457351538 --search-especialidade cardiologia --search-cidade "feira de santana" --search-bairro Centro
```

## Realistic mode vs aggressive mode

`load-tools.js` supports two pacing modes:

- Realistic mode
  - Default.
  - Sleeps a random 4 to 12 seconds between iterations.
  - Better approximation for simultaneous voice calls that do not all fire tool requests continuously.
- Aggressive mode
  - Enabled with `AGGRESSIVE_MODE=true` or `-AggressiveMode` / `--aggressive`.
  - Sleeps 1 second between iterations.
  - Useful for stress testing, but easier to overload upstream dependencies.

## Search payload mode

By default, `load-tools.js` and `load-idempotency.js` use the known functional PB Saude search payload:

```json
{
  "cpf": "03457351538",
  "especialidade": "cardiologia",
  "cidade": "feira de santana",
  "bairro": "Centro"
}
```

This is the right default for validating the real external API path because a syntactically valid CPF may still be rejected by the upstream system.

Use randomized search arguments only for mock, staging, or seeded test environments:

```powershell
.\scripts\load\run-load-tests.ps1 -BaseUrl http://127.0.0.1:8000 -Mode tools -RandomizeSearchArgs
```

## Scenarios and thresholds

### `load-tools.js`

- 1 minute to 10 VUs
- 2 minutes to 30 VUs
- 2 minutes to 60 VUs
- 3 minutes to 100 VUs
- 3 minutes sustaining 100 VUs
- 1 minute ramp down

Thresholds:

- `http_req_failed < 1%`
- `p95 < 2000ms`
- `p99 < 3000ms`

### `load-idempotency.js`

- 20 VUs for 1 minute

Thresholds:

- `http_req_failed < 1%`
- `p95 < 1000ms`

### `load-health.js`

- 50 VUs for 1 minute
- Baseline sanity only

## How to interpret the results

- `http_req_duration`
  - End-to-end request latency seen by k6.
- `p95`
  - 95% of requests finished under this duration.
  - This is the main operational latency indicator.
- `p99`
  - 99% of requests finished under this duration.
  - Sensitive to tail latency and saturation.
- `http_req_failed`
  - Fraction of failed HTTP requests.
  - Includes transport and threshold-visible request failures.
- `checks`
  - Fraction of assertion checks that passed inside the k6 script.
  - If checks fail while HTTP stays 200, the app may still be returning malformed or degraded payloads.
- `dropped_iterations`
  - Iterations that could not start as planned.
  - Often indicates the generator is saturated or the scenario is too aggressive for the current pacing.

Good target values:

- failure rate `< 1%`
- `p95 < 2s`
- `p99 < 3s`

Warning signs:

- `p95 > 4s`
- `p99 > 6s`
- `http_req_failed > 1%`
- many `TIMEOUT` or `UPSTREAM_503` events
- CPU above `80%`
- Postgres connection pool exhaustion

## What to monitor during the test

- `docker stats`
- application logs
- Postgres logs
- `/ops/dashboard/health`
- `/ops/dashboard/resilience`

Suggested live checklist:

1. Watch container CPU and memory
2. Watch app logs for `TIMEOUT`, `UPSTREAM_503`, `tenant_resolution_rejected`, and webhook failures
3. Watch Postgres connections, slow queries, and pool exhaustion
4. Compare `/ops/dashboard/health` and `/ops/dashboard/resilience` before and after the run

## Production safety

- Start with `health`, then a small `tools` run, then the full ramp.
- Prefer staging before production.
- Avoid aggressive mode in production peak hours.
- If the external PB Saude API is shared with live traffic, coordinate the test window.
- If `DB_ENABLED=true`, make sure the database pool settings are compatible with the intended concurrency before jumping to 100 VUs.
