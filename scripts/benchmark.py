"""Compare authenticated /users/me calls directly and through the gateway."""
import argparse
import json
import math
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


def summarize(values):
    ordered = sorted(values)
    return {
        "mean_ms": round(statistics.mean(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[math.ceil(len(values) * 0.95) - 1], 3),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://127.0.0.1:8000")
    parser.add_argument("--users", default="http://127.0.0.1:8001")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--interval", type=float, default=0.12)
    parser.add_argument("--output", default="reports/latency.json")
    args = parser.parse_args()
    if args.requests < 1 or args.interval < 0.11:
        parser.error("Use at least one request and an interval >= 0.11 seconds for the 10 req/s limit")
    gateway, users = args.gateway.rstrip("/"), args.users.rstrip("/")
    with httpx.Client(timeout=15, trust_env=False) as client:
        username = f"bench-{uuid.uuid4().hex[:16]}"
        password = uuid.uuid4().hex
        registration = client.post(f"{gateway}/users/register", json={
            "username": username, "password": password, "name": "Latency benchmark",
        })
        registration.raise_for_status()
        login = client.post(f"{gateway}/users/login", json={"username": username, "password": password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        time.sleep(1.05)

        def measure(base):
            start = time.perf_counter()
            response = client.get(f"{base}/users/me", headers=headers)
            elapsed = (time.perf_counter() - start) * 1000
            response.raise_for_status()
            assert response.json()["username"] == username
            return elapsed

        for _ in range(5):
            measure(users)
            measure(gateway)
            time.sleep(args.interval)
        direct, proxied = [], []
        for index in range(args.requests):
            # Alternate the order to reduce bias from always measuring one path first.
            if index % 2:
                proxied.append(measure(gateway))
                direct.append(measure(users))
            else:
                direct.append(measure(users))
                proxied.append(measure(gateway))
            time.sleep(args.interval)
    direct_stats, gateway_stats = summarize(direct), summarize(proxied)
    report = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": "/users/me", "requests_per_path": args.requests,
        "warmup_requests_per_path": 5, "interval_seconds": args.interval,
        "direct_url": users, "gateway_url": gateway,
        "methodology": "Sequential paired requests, alternating order, persistent HTTP connections. Direct service validates JWT; gateway validates JWT and forwards trusted identity. Failed requests are not included: they abort the run.",
        "direct": direct_stats, "gateway": gateway_stats,
        "mean_overhead_ms": round(statistics.mean(proxied) - statistics.mean(direct), 3),
        "samples_ms": {"direct": direct, "gateway": proxied},
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    markdown = [
        "# Gateway latency measurement", "", f"Measured: {report['measured_at_utc']}", "",
        f"{args.requests} successful requests per path to `/users/me`, after 5 warm-up requests.", "",
        "| Path | Mean (ms) | Median (ms) | p95 (ms) |", "|---|---:|---:|---:|",
        f"| Direct User service | {direct_stats['mean_ms']} | {direct_stats['median_ms']} | {direct_stats['p95_ms']} |",
        f"| Through gateway | {gateway_stats['mean_ms']} | {gateway_stats['median_ms']} | {gateway_stats['p95_ms']} |",
        "", f"Mean gateway overhead: **{report['mean_overhead_ms']} ms**.", "",
        report["methodology"], "",
        f"Pairs are separated by {args.interval}s to respect the 10 req/s rate limit. These local measurements depend on machine load and are not a production capacity test.",
    ]
    output.with_suffix(".md").write_text("\n".join(markdown) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "samples_ms"}, indent=2))


if __name__ == "__main__":
    main()
