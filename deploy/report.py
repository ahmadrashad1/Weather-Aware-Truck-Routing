#!/usr/bin/env python3
"""Summarise the backend's JSON logs. Runs on the server with only the standard library.

    docker logs truck-routing-backend-1 2>&1 | python3 deploy/report.py

Logs start again whenever the container is replaced, so an update empties this report.
"""

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

DAY = timedelta(hours=24)
HOUR = timedelta(hours=1)


def percentile(ordered: list[float], share: int) -> float:
    return ordered[max(math.ceil(len(ordered) * share / 100) - 1, 0)]


def read_events(lines, now):
    for line in lines:
        try:
            event = json.loads(line)
            event["_when"] = datetime.fromisoformat(event["time"])
        except (ValueError, KeyError, TypeError):
            continue
        if now - event["_when"] <= DAY:
            yield event


def latency_table(title, rows):
    print(f"{title}\n  {'name':<28}{'count':>7}{'p50':>8}{'p95':>8}{'p99':>8}")
    for name, values in sorted(rows.items()):
        ordered = sorted(values)
        cells = "".join(f"{round(percentile(ordered, share)):>8}" for share in (50, 95, 99))
        print(f"  {name:<28}{len(ordered):>7}{cells}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", type=datetime.fromisoformat, default=datetime.now(UTC))
    now = parser.parse_args().now

    latency = defaultdict(list)
    statuses = Counter()
    provider_latency = defaultdict(list)
    provider_failures = Counter()
    refusals = Counter()
    breakers = Counter()
    vitals = defaultdict(list)
    cached = fetched = fetched_last_hour = waits = deadlines = 0
    earliest = None

    for event in read_events(sys.stdin, now):
        earliest = min(earliest or event["_when"], event["_when"])
        name = event.get("event")
        if name == "request":
            latency[event["path"]].append(event["duration_ms"])
            statuses[event["status"]] += 1
            cached += event.get("weather_cells_cached", 0)
            locations = event.get("weather_cells_fetched", 0)
            fetched += locations
            if now - event["_when"] <= HOUR:
                fetched_last_hour += locations
        elif name == "provider_call":
            provider_latency[event["provider"]].append(event["duration_ms"])
            if "error" in event or event.get("status", 0) >= 500:
                provider_failures[event["provider"]] += 1
        elif name == "weather_budget_refused":
            refusals[f"{event['window']}, {event['purpose']}"] += 1
        elif name == "circuit_opened":
            breakers[event["provider"]] += 1
        elif name == "web_vital":
            vitals[event["name"]].append(event["value"])
        elif name == "weather_rate_limit_wait":
            waits += 1
        elif name == "weather_deadline_reached":
            deadlines += 1

    if not latency:
        print("No requests in the last 24 hours of these logs.\n")
    else:
        print(f"Logs cover the last 24 hours, starting {earliest:%Y-%m-%d %H:%M} UTC.\n")
        latency_table("Requests, milliseconds", latency)
        print("\nStatus codes: " + ", ".join(f"{k}: {v}" for k, v in sorted(statuses.items())))

    total = cached + fetched
    if total:
        print(f"\nWeather cache hit rate: {round(cached / total * 100)}%")
    print(f"Forecast locations fetched: last hour {fetched_last_hour}, last 24 hours {fetched}")
    print(f"Rate limit waits: {waits}. Deadlines reached: {deadlines}.")

    if provider_latency:
        print()
        latency_table("Provider calls, milliseconds", provider_latency)
        print("Failures: " + (", ".join(f"{k}: {v}" for k, v in provider_failures.items()) or "0"))
    if refusals:
        print("\nBudget refusals: " + ", ".join(f"{k}: {v}" for k, v in refusals.items()))
    if breakers:
        print("\nCircuit breaker opened: " + ", ".join(f"{k}: {v}" for k, v in breakers.items()))
    if vitals:
        print("\nBrowser vitals, p75 (CLS is a score, the rest are milliseconds)")
        for name, values in sorted(vitals.items()):
            ordered = sorted(values)
            print(f"  {name:<6}{percentile(ordered, 75):>10.3f}  ({len(ordered)} samples)")


if __name__ == "__main__":
    main()
