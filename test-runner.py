#!/usr/bin/env python3
"""
test-runner.py — Standalone test runner for the ExpertMind Incident Platform.

Sends predefined alert scenarios to the running platform services, checks health,
sets up on-call schedules, and optionally runs AI analysis on each alert.

Usage:
    python3 test-runner.py                  # Send all scenarios + health check
    python3 test-runner.py --health         # Health check only
    python3 test-runner.py --scenario cpu-high
    python3 test-runner.py --setup-oncall   # Push on-call schedules
    python3 test-runner.py --list           # List available scenarios
    python3 test-runner.py --continuous 10  # Send random alerts every 10s

Environment variables (optional):
    ALERT_URL       (default: http://localhost:8001/api/v1/alerts)
    AI_ANALYSIS_URL (default: http://localhost:8005/api/v1/analyze)
    ONCALL_URL      (default: http://localhost:8003/api/v1/oncall)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import time
from urllib.request import Request, urlopen

# ── Configuration ────────────────────────────────────────────

ALERT_URL = os.getenv("ALERT_URL", "http://localhost:8001/api/v1/alerts")
AI_ANALYSIS_URL = os.getenv("AI_ANALYSIS_URL", "http://localhost:8005/api/v1/analyze")
ONCALL_URL = os.getenv("ONCALL_URL", "http://localhost:8003/api/v1")

HEALTH_ENDPOINTS = {
    "alert-ingestion": "http://localhost:8001/health",
    "incident-management": "http://localhost:8002/health",
    "oncall-service": "http://localhost:8003/health",
    "notification-service": "http://localhost:8004/health",
    "ai-analysis": "http://localhost:8005/health",
}

# ── Color helpers ────────────────────────────────────────────

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}OK{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}WARN{RESET} {msg}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{CYAN}── {msg} ──{RESET}")


# ── Test Scenarios ───────────────────────────────────────────

SCENARIOS = [
    {
        "id": "cpu-high",
        "category": "CPU",
        "service": "payment-api",
        "severity": "critical",
        "message": "CPU utilization at 98% on payment-api-pod-3. Process java consuming 95% CPU.",
        "labels": {"env": "production", "region": "us-east-1"},
    },
    {
        "id": "cpu-spike",
        "category": "CPU",
        "service": "payment-api",
        "severity": "critical",
        "message": "CPU spike detected on payment-api-pod-1. Load average 12.5 (4 cores).",
        "labels": {"env": "production", "region": "us-east-1"},
    },
    {
        "id": "mem-pressure",
        "category": "Memory",
        "service": "payment-api",
        "severity": "critical",
        "message": "Memory pressure on payment-api: RSS at 3.8GB / 4GB limit. OOM kill imminent.",
        "labels": {"env": "production", "region": "us-east-1"},
    },
    {
        "id": "latency-spike",
        "category": "Latency",
        "service": "payment-api",
        "severity": "critical",
        "message": "P99 latency for payment-api jumped to 8.2s (SLO: 500ms). 40% of requests affected.",
        "labels": {"env": "production", "region": "us-east-1"},
    },
    {
        "id": "error-rate",
        "category": "HTTP",
        "service": "payment-api",
        "severity": "critical",
        "message": "Error rate spike: 500 Internal Server Error rate at 32% on payment-api over last 5 minutes.",
        "labels": {"env": "production", "region": "us-east-1"},
    },
    {
        "id": "pod-restart",
        "category": "Kubernetes",
        "service": "payment-api",
        "severity": "critical",
        "message": "Pod crash loop: payment-api-pod-5 restarted 12 times in 10 minutes. Exit code 137 (OOMKilled).",
        "labels": {"env": "production", "region": "us-east-1"},
    },
]

ONCALL_SCHEDULES = [
    {
        "team": "payment-api",
        "rotation_type": "weekly",
        "start_date": "2026-02-10",
        "engineers": [
            {"name": "Omar Afidi", "email": "omarafidi2005@gmail.com", "primary": True},
        ],
        "escalation_minutes": 5,
    },
]

# ── HTTP helpers (stdlib only — no pip deps) ─────────────────


def _post(url: str, data: dict, timeout: int = 10) -> dict | None:
    body = json.dumps(data).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        fail(f"{url} → {exc}")
        return None


def _get(url: str, timeout: int = 5) -> dict | None:
    try:
        with urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ── Commands ─────────────────────────────────────────────────


def cmd_health() -> bool:
    """Check health of all services. Returns True if all healthy."""
    header("Health Check")
    all_ok = True
    for name, url in HEALTH_ENDPOINTS.items():
        data = _get(url)
        if data and data.get("status") == "healthy":
            ok(name)
        else:
            fail(name)
            all_ok = False
    return all_ok


def cmd_list() -> None:
    """List available scenarios."""
    header("Available Scenarios")
    for s in SCENARIOS:
        sev_color = RED if s["severity"] in ("critical", "high") else YELLOW
        print(
            f"  {CYAN}{s['id']:16s}{RESET}  {sev_color}{s['severity']:8s}{RESET}  {s['service']:20s}  {s['message'][:60]}"
        )


def cmd_send(scenario_id: str | None = None) -> dict:
    """Send one scenario or all. Returns stats dict."""
    targets = SCENARIOS
    if scenario_id:
        targets = [s for s in SCENARIOS if s["id"] == scenario_id]
        if not targets:
            fail(f"Unknown scenario: {scenario_id}")
            return {"sent": 0, "failed": 1, "analysed": 0}

    header(f"Sending {'1 scenario' if scenario_id else f'all {len(targets)} scenarios'}")
    stats = {"sent": 0, "failed": 0, "analysed": 0}

    for s in targets:
        payload = {
            "service": s["service"],
            "severity": s["severity"],
            "message": s["message"],
            "labels": s.get("labels", {}),
            "category": s.get("category"),
        }
        result = _post(ALERT_URL, payload)
        if result is None:
            stats["failed"] += 1
            continue

        alert_id = result.get("alert_id", "?")
        incident_id = result.get("incident_id", "?")
        ok(f"{s['id']:16s}  alert={alert_id}  incident={incident_id}")
        stats["sent"] += 1

        # Try AI analysis
        ai_payload = {
            "message": s["message"],
            "service": s["service"],
            "severity": s["severity"],
            "alert_id": alert_id,
            "incident_id": incident_id,
        }
        ai_result = _post(AI_ANALYSIS_URL, ai_payload)
        if ai_result and ai_result.get("suggestions"):
            suggestions = ai_result["suggestions"][:2]
            for sg in suggestions:
                print(f"         💡 {sg}")
            stats["analysed"] += 1

        time.sleep(0.3)

    header("Summary")
    print(f"  Sent: {stats['sent']}  |  Analysed: {stats['analysed']}  |  Failed: {stats['failed']}")
    return stats


def cmd_setup_oncall() -> None:
    """Push on-call schedules to the on-call service."""
    header("Setting Up On-Call Schedules")
    for sched in ONCALL_SCHEDULES:
        result = _post(f"{ONCALL_URL}/schedules", sched)
        primary = next((e["name"] for e in sched["engineers"] if e.get("primary")), sched["engineers"][0]["name"])
        if result:
            ok(f"{sched['team']:12s} → {primary}")
        else:
            fail(f"{sched['team']:12s} → {primary}")


def cmd_continuous(interval: int) -> None:
    """Send random alerts at interval. Ctrl+C to stop."""
    header(f"Continuous Mode (every {interval}s) — Ctrl+C to stop")
    count = 0
    running = True

    def _stop(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        s = random.choice(SCENARIOS)
        count += 1
        payload = {
            "service": s["service"],
            "severity": s["severity"],
            "message": s["message"],
            "labels": s.get("labels", {}),
            "category": s.get("category"),
        }
        result = _post(ALERT_URL, payload)
        if result:
            ok(f"#{count} {s['id']:16s} alert={result.get('alert_id', '?')}")
        else:
            fail(f"#{count} {s['id']}")

        for _ in range(interval * 10):
            if not running:
                break
            time.sleep(0.1)

    print(f"\n  Stopped after {count} alerts.")


# ── Main ─────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="ExpertMind Test Runner — send test alerts to the platform")
    parser.add_argument("--health", action="store_true", help="Check health of all services")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    parser.add_argument("--scenario", type=str, help="Send a specific scenario by ID")
    parser.add_argument("--all", action="store_true", help="Send all scenarios (default if no flags)")
    parser.add_argument("--setup-oncall", action="store_true", help="Push on-call schedules")
    parser.add_argument(
        "--continuous", type=int, metavar="SEC", help="Continuous mode: send random alert every SEC seconds"
    )

    args = parser.parse_args()

    # If no flags, run health + send all
    if not any([args.health, args.list, args.scenario, args.all, args.setup_oncall, args.continuous is not None]):
        args.health = True
        args.all = True

    if args.health:
        cmd_health()

    if args.list:
        cmd_list()

    if args.setup_oncall:
        cmd_setup_oncall()

    if args.scenario:
        cmd_send(args.scenario)

    if args.all:
        cmd_send()

    if args.continuous is not None:
        cmd_continuous(args.continuous)


if __name__ == "__main__":
    main()
