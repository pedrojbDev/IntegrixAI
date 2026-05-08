from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    duration_ms: float
    detail: str


class SmokeFailure(Exception):
    pass


def main() -> int:
    env = load_env(ROOT / ".env")
    args = parse_args(env)
    results: list[CheckResult] = []

    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        checks = [
            ("health", lambda: check_health(client)),
            ("handoff", lambda: check_handoff(client, args)),
            ("search", lambda: check_search(client, args)),
            ("dashboard", lambda: check_dashboard(client, args)),
            ("light_load", lambda: check_light_load(args)),
        ]

        for name, fn in checks:
            results.append(run_check(name, fn))

    print_summary(results)
    return 0 if all(item.ok for item in results) else 1


def parse_args(env: dict[str, str]) -> argparse.Namespace:
    tenant_id = infer_tenant_id(env)
    parser = argparse.ArgumentParser(
        description="Smoke local do IntegrixAI: health, tools, dashboard e carga leve."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--webhook-secret", default=env.get("WEBHOOK_SECRET", ""))
    parser.add_argument("--webhook-secret-header", default=env.get("WEBHOOK_SECRET_HEADER", "x-webhook-secret"))
    parser.add_argument("--ops-token", default=env.get("OPS_DASHBOARD_TOKEN", ""))
    parser.add_argument("--ops-token-header", default=env.get("OPS_TOKEN_HEADER", "x-ops-token"))
    parser.add_argument("--tenant-id", default=tenant_id)
    parser.add_argument("--to-number", default=infer_to_number(env) or "+5511999999999")
    parser.add_argument("--cpf", default="03457351538")
    parser.add_argument("--cidade", default="feira de santana")
    parser.add_argument("--bairro", default="Centro")
    parser.add_argument("--especialidade", default="cardiologia")
    parser.add_argument("--load-calls", type=int, default=20)
    parser.add_argument("--load-workers", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args()


def load_env(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def infer_tenant_id(env: dict[str, str]) -> str:
    tenant_map_raw = env.get("TENANT_MAP", "")
    try:
        tenant_map = json.loads(tenant_map_raw) if tenant_map_raw else {}
    except json.JSONDecodeError:
        tenant_map = {}
    if isinstance(tenant_map, dict) and tenant_map:
        first_value = next(iter(tenant_map.values()))
        if isinstance(first_value, str) and first_value.strip():
            return first_value.strip()
    return env.get("DEFAULT_TENANT", "demo")


def infer_to_number(env: dict[str, str]) -> str | None:
    tenant_map_raw = env.get("TENANT_MAP", "")
    try:
        tenant_map = json.loads(tenant_map_raw) if tenant_map_raw else {}
    except json.JSONDecodeError:
        return None
    if isinstance(tenant_map, dict) and tenant_map:
        first_key = next(iter(tenant_map.keys()))
        return str(first_key)
    return None


def run_check(name: str, fn) -> CheckResult:
    started_at = time.perf_counter()
    try:
        detail = fn()
        return CheckResult(name, True, elapsed_ms(started_at), detail)
    except Exception as exc:
        return CheckResult(name, False, elapsed_ms(started_at), str(exc))


def check_health(client: httpx.Client) -> str:
    response = client.get("/health")
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "ok":
        raise SmokeFailure(f"health status inesperado: {data!r}")
    return f"environment={data.get('environment')} data_mode={data.get('data_mode')}"


def check_handoff(client: httpx.Client, args: argparse.Namespace) -> str:
    call_id = unique_call_id("smoke_handoff")
    data = post_tool(
        client,
        args,
        call_id=call_id,
        tool_call_id="tc_handoff",
        tool_name="handoff_human",
        arguments={"reason": "smoke local"},
    )
    result = first_result(data)
    assert_tool_ok(result, "handoff_human")
    return f"call_id={call_id}"


def check_search(client: httpx.Client, args: argparse.Namespace) -> str:
    call_id = unique_call_id("smoke_search")
    data = post_tool(
        client,
        args,
        call_id=call_id,
        tool_call_id="tc_search",
        tool_name="search_providers",
        arguments={
            "cpf": args.cpf,
            "cidade": args.cidade,
            "bairro": args.bairro,
            "especialidade": args.especialidade,
        },
    )
    result = first_result(data)
    assert_tool_ok(result, "search_providers")
    providers = result["result"].get("data", {}).get("providers", [])
    return f"call_id={call_id} providers={len(providers)}"


def check_dashboard(client: httpx.Client, args: argparse.Namespace) -> str:
    if not args.ops_token:
        raise SmokeFailure("OPS_DASHBOARD_TOKEN ausente; use --ops-token")
    response = client.get(
        "/ops/dashboard/overview",
        params={"tenant_id": args.tenant_id},
        headers={args.ops_token_header: args.ops_token},
    )
    response.raise_for_status()
    data = response.json()
    if "kpis" not in data:
        raise SmokeFailure(f"dashboard sem kpis: {data!r}")
    kpis = data["kpis"]
    return f"tenant_id={data.get('tenant_id')} total_calls={kpis.get('total_calls')}"


def check_light_load(args: argparse.Namespace) -> str:
    total = max(1, args.load_calls)
    workers = max(1, min(args.load_workers, total))

    def run_one(index: int) -> None:
        with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
            call_id = unique_call_id(f"smoke_load_{index}")
            data = post_tool(
                client,
                args,
                call_id=call_id,
                tool_call_id=f"tc_load_{index}",
                tool_name="handoff_human",
                arguments={"reason": "smoke load local"},
            )
            assert_tool_ok(first_result(data), "handoff_human")

    started_at = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_one, index) for index in range(total)]
        failures = []
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures.append(str(exc))

    if failures:
        raise SmokeFailure(f"{len(failures)}/{total} falharam: {failures[:3]}")
    duration_ms = elapsed_ms(started_at)
    return f"calls={total} workers={workers} avg_ms={duration_ms / total:.2f}"


def post_tool(
    client: httpx.Client,
    args: argparse.Namespace,
    *,
    call_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    headers = {}
    if args.webhook_secret:
        headers[args.webhook_secret_header] = args.webhook_secret

    response = client.post(
        "/tools",
        headers=headers,
        json={
            "message": {
                "call": {"id": call_id, "to": args.to_number},
                "toolCallList": [
                    {
                        "id": tool_call_id,
                        "name": tool_name,
                        "arguments": arguments,
                    }
                ],
            }
        },
    )
    response.raise_for_status()
    data = response.json()
    if "results" not in data:
        raise SmokeFailure(f"resposta sem results: {data!r}")
    return data


def first_result(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results") or []
    if not results:
        raise SmokeFailure(f"results vazio: {data!r}")
    return results[0]


def assert_tool_ok(item: dict[str, Any], expected_tool: str) -> None:
    result = item.get("result") or {}
    if result.get("tool_name") != expected_tool:
        raise SmokeFailure(f"tool inesperada: {result!r}")
    if result.get("ok") is not True:
        raise SmokeFailure(f"tool falhou: {result!r}")


def unique_call_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def print_summary(results: list[CheckResult]) -> None:
    print("\nSmoke local")
    print("=" * 72)
    for item in results:
        status = "OK" if item.ok else "FAIL"
        print(f"{status:4} {item.name:12} {item.duration_ms:8.2f} ms  {item.detail}")
    print("=" * 72)


if __name__ == "__main__":
    sys.exit(main())
