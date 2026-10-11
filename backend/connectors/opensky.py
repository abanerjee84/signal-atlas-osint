import time
from collections import deque
from datetime import datetime, timezone

from ..models import AircraftMetadata, Report
from .base import Connector, SafeHTTP, box, spatial_sample


class OpenSky(Connector):
    source_id, name, category = "opensky", "OpenSky aircraft observations", "aviation"
    homepage = "https://opensky-network.org/about/faq"
    interval = 30
    live_aircraft = True

    def __init__(self, settings):
        super().__init__(settings)
        self.interval = settings.opensky_poll_seconds
        self._token = None
        self._token_until = 0

    # Aircraft positions are a continuous sample, not discrete incidents. Storing
    # the full global snapshot every cycle lets one feed dominate totals, storage
    # and query cost, so only this many positions are kept per collection. Cells
    # are still sampled round-robin so coverage stays worldwide.
    per_cycle_cap = 1000
    limitation = "Worldwide network or configured region; all reported classes with reported position and ground track only, capped at 1000 current positions and sampled across classes and geographic cells. Current snapshot refreshes every 30 seconds by default while a visible live Aviation layer requests it; provider quota backoff applies. Retained history every 30 minutes. Unknown ground tracks are excluded; class and registry military filters are applied in the dashboard. Public ADS-B has coverage gaps. Map symbols rotate by reported ground track, not nose heading. Registration country is not departure origin; airports are not provided. Historical storage subject to your provider agreement."

    def metadata(self):
        return {
            **super().metadata(),
            "coverage_scope": "world" if self.settings.opensky_bbox == "world" else "regional",
            "coverage_area": self.settings.opensky_bbox,
            "record_selection": "all_classes_with_reported_track_class_geographic_sample",
            "aircraft_categories": list(range(21)),
            "per_cycle_cap": self.per_cycle_cap,
        }

    def select_records(self, records):
        limit = min(self.per_cycle_cap, self.settings.max_records)
        classes = {}
        for record in records:
            if self.displayable(record):
                classes.setdefault(record["state"][17], []).append(record)
        groups = [deque(spatial_sample(group, limit, lambda record: (record["state"][5], record["state"][6])))
                  for group in classes.values()]
        selected = []
        while groups and len(selected) < limit:
            for group in groups:
                selected.append(group.popleft())
                if len(selected) == limit:
                    break
            groups = [group for group in groups if group]
        return selected

    @staticmethod
    def displayable(record):
        state = record.get("state", [])
        return (
            len(state) > 17
            and (state[17] is None or isinstance(state[17], int) and 0 <= state[17] <= 20)
            and state[3] is not None
            and state[5] is not None
            and state[6] is not None
            and isinstance(state[10], (int, float))
            and 0 <= state[10] < 360
        )

    def access(self):
        return (
            None
            if self.settings.opensky_client_id and self.settings.opensky_client_secret
            else "OpenSky OAuth API client credentials and permitted retention required"
        )

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        params = {"extended": 1}
        if self.settings.opensky_bbox != "world":
            west, south, east, north = box(self.settings.opensky_bbox)
            params.update({"lamin": south, "lomin": west, "lamax": north, "lomax": east})
        if not self._token or time.monotonic() >= self._token_until:
            token = await http.json(
                "POST",
                "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.opensky_client_id,
                    "client_secret": self.settings.opensky_client_secret,
                },
                attempts=1,
            )
            self._token = token["access_token"]
            self._token_until = time.monotonic() + max(
                0, min(1800, float(token.get("expires_in", 1800))) - 30
            )
        result = await http.json(
            "GET",
            "https://opensky-network.org/api/states/all",
            headers={"Authorization": f"Bearer {self._token}"},
            params=params,
            attempts=1,
        )
        return [{"state": state, "time": result["time"]} for state in result.get("states") or []]

    def normalize(self, record: dict) -> Report:
        state = record["state"]
        if state[3] is None or state[5] is None or state[6] is None:
            raise ValueError("No reported position")
        # state[10] is true track in degrees clockwise from north. It is a
        # ground track, not the aircraft's nose heading or a planned route.
        track = state[10] if len(state) > 10 else None
        track = float(track) if track is not None else None
        if track is not None and not 0 <= track < 360:
            track = None
        category = state[17] if len(state) > 17 else None
        return Report(
            external_id=f"{state[0]}:{state[3]}",
            source_id=self.source_id,
            source_url="https://opensky-network.org/network/explorer",
            title=f"Aircraft {(state[1] or '').strip() or state[0]}",
            description=f"ICAO24 {state[0]}; registration country {state[2]}; altitude {state[7]} m; velocity {state[9]} m/s. Registration country is not position country.",
            category=self.category,
            longitude=state[5],
            latitude=state[6],
            location_precision="approximate",
            location_basis="Public ADS-B reported position; incomplete coverage",
            occurred_at=datetime.fromtimestamp(state[3], timezone.utc),
            published_at=datetime.fromtimestamp(record["time"], timezone.utc),
            aircraft_track_deg=track,
            aircraft_callsign=(state[1] or "").strip()[:20],
            aircraft_category=category if isinstance(category, int) else None,
            aircraft=AircraftMetadata(
                icao24=state[0],
                registration_country=state[2] or "Unknown",
                barometric_altitude_m=state[7],
                geometric_altitude_m=state[13] if len(state) > 13 else None,
                speed_mps=state[9],
                vertical_rate_mps=state[11] if len(state) > 11 else None,
                on_ground=state[8],
                last_contact=datetime.fromtimestamp(state[4], timezone.utc) if state[4] else None,
            ),
            tags=["ads-b", state[0]],
            raw=record,
        )
