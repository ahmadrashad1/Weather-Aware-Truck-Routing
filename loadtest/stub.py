#!/usr/bin/env python3
"""A stand-in for TomTom and Open-Meteo, so load tests spend no quota and reach neither service.

It invents all its data, because TomTom's terms don't allow storing its results. Routes have about
as many points as real ones, and delays match the live server's report. Change its behaviour while
it runs:

    curl -X POST 'localhost:9000/__control?mode=hang'          # ok, hang or error
    curl -X POST 'localhost:9000/__control?delay_scale=10'     # Slow every response tenfold
    curl -X POST 'localhost:9000/__control?minute_limit=600'   # Locations a minute, 0 for no limit
"""

import json
import math
import os
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

MILES_PER_DEGREE = 69.09
METERS_PER_MILE = 1609.344
EARTH_RADIUS_MILES = 3958.8
# A long real route has about 40,000 points in about 2,500 miles.
POINTS_PER_MILE = 16
TRUCK_MPH = 55
ROAD_FACTOR = 1.2
# Seconds, from the live server's report.
DELAY = {"route": 0.9, "search": 0.25, "caption": 0.25, "forecast": 0.8}

state = {"mode": "ok", "delay_scale": 1.0, "minute_limit": 0}
locations_this_minute = [0, 0]  # Minute, count.
counts = {"locations": 0, "routes": 0, "searches": 0, "limited": 0}
lock = threading.Lock()
hang_release = threading.Event()


def miles_between(a, b):
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (*a, *b))
    chord = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(chord))


def invent_route(origin, destination, bow):
    """A wiggly line between two points, bowed sideways so that alternatives differ."""
    miles = miles_between(origin, destination) * ROAD_FACTOR * (1 + 0.05 * abs(bow))
    count = max(int(miles * POINTS_PER_MILE), 2)
    span = max(abs(destination[0] - origin[0]), abs(destination[1] - origin[1]), 0.5)
    points = []
    for index in range(count):
        share = index / (count - 1)
        arch = math.sin(math.pi * share)
        lat = origin[0] + (destination[0] - origin[0]) * share + bow * span * 0.12 * arch
        lon = origin[1] + (destination[1] - origin[1]) * share
        lat += 0.01 * math.sin(share * miles / 3) * arch
        lon += 0.01 * math.cos(share * miles / 5) * arch
        points.append({"latitude": round(lat, 5), "longitude": round(lon, 5)})
    seconds = int(miles / TRUCK_MPH * 3600)
    meters = int(miles * METERS_PER_MILE)
    steps = max(int(miles / 10), 1)
    return {
        "summary": {"lengthInMeters": meters, "travelTimeInSeconds": seconds},
        "legs": [{"points": points}],
        "guidance": {
            "instructions": [
                {
                    "routeOffsetInMeters": meters * step // steps,
                    "travelTimeInSeconds": seconds * step // steps,
                }
                for step in range(1, steps)
            ]
        },
    }


@lru_cache(maxsize=64)
def route_body(stops, alternatives):
    origin, destination = stops[0], stops[-1]
    bows = (0, 1, -1)[: alternatives + 1]
    return json.dumps({"routes": [invent_route(origin, destination, bow) for bow in bows]}).encode()


@lru_cache(maxsize=16)
def forecast_series(day, variant, days):
    """The arrays for one location, as text, so that a batch of 100 costs almost no CPU here."""
    start = day * 86400
    hours = days * 24
    wind = [round(6 + variant * 4 + 3 * math.sin(hour / 6), 1) for hour in range(hours)]
    rain = [round(0.6 * variant * max(math.sin(hour / 11), 0), 2) for hour in range(hours)]
    return json.dumps(
        {
            "time": [start + hour * 3600 for hour in range(hours)],
            "wind_speed_10m": wind,
            "rain": rain,
            "showers": [0.0] * hours,
            "snowfall": [0.0] * hours,
        }
    )


def forecast_body(lats, lons, days):
    day = int(time.time() // 86400)
    items = []
    for lat, lon in zip(lats, lons, strict=True):
        variant = int(abs(float(lat) * 20 + float(lon) * 20)) % 4
        series = forecast_series(day, variant, days)
        items.append(f'{{"latitude":{lat},"longitude":{lon},"hourly":{series}}}')
    text = items[0] if len(items) == 1 else "[" + ",".join(items) + "]"
    return text.encode()


def over_minute_limit(locations):
    limit = state["minute_limit"]
    with lock:
        counts["locations"] += locations
        minute = int(time.time() // 60)
        if locations_this_minute[0] != minute:
            locations_this_minute[:] = [minute, 0]
        if limit and locations_this_minute[1] + locations > limit:
            counts["limited"] += 1
            counts["locations"] -= locations
            return True
        locations_this_minute[1] += locations
    return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def send_json(self, body, status=200, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        query = parse_qs(urlparse(self.path).query)
        if "mode" in query:
            state["mode"] = query["mode"][0]
            if state["mode"] == "ok":
                hang_release.set()
                hang_release.clear()
        if "delay_scale" in query:
            state["delay_scale"] = float(query["delay_scale"][0])
        if "minute_limit" in query:
            state["minute_limit"] = int(query["minute_limit"][0])
        self.send_json(json.dumps({**state, **counts}).encode())

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/__control":
            self.send_json(json.dumps({**state, **counts}).encode())
            return
        if url.path.startswith("/routing/1/calculateRoute/"):
            kind = "route"
        elif url.path.startswith("/search/2/search/"):
            kind = "search"
        elif url.path == "/map/1/copyrights/caption.json":
            kind = "caption"
        elif url.path == "/v1/forecast":
            kind = "forecast"
        else:
            self.send_json(b"{}", 404)
            return

        if state["mode"] == "hang":
            hang_release.wait(600)
        if state["mode"] == "error":
            self.send_json(b"{}", 503)
            return
        time.sleep(DELAY[kind] * state["delay_scale"])
        getattr(self, f"answer_{kind}")(url, query)

    def answer_route(self, url, query):
        counts["routes"] += 1
        stops = unquote(url.path.split("/")[4]).split(":")
        points = tuple(tuple(map(float, stop.split(","))) for stop in stops)
        alternatives = int(query.get("maxAlternatives", ["0"])[0])
        self.send_json(route_body(points, alternatives))

    def answer_search(self, url, _query):
        counts["searches"] += 1
        text = unquote(url.path.split("/")[-1]).removesuffix(".json")
        result = {
            "address": {"freeformAddress": f"{text}, TX"},
            "position": {"lat": 32.78, "lon": -96.8},
        }
        self.send_json(json.dumps({"results": [result]}).encode())

    def answer_caption(self, _url, _query):
        self.send_json(b'{"copyrightsCaption":"Stub"}', headers=[("Cache-Control", "max-age=86400")])

    def answer_forecast(self, _url, query):
        lats = query["latitude"][0].split(",")
        lons = query["longitude"][0].split(",")
        if over_minute_limit(len(lats)):
            reason = b'{"error":true,"reason":"Minutely API request limit exceeded."}'
            self.send_json(reason, 429)
            return
        self.send_json(forecast_body(lats, lons, int(query.get("forecast_days", ["16"])[0])))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 512


def main():
    Server(("0.0.0.0", int(os.environ.get("PORT", "9000"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
