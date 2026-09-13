from __future__ import annotations

import argparse
import gzip
import importlib
import ipaddress
import json
import math
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
CONTINENTS = {"AF", "AN", "AS", "EU", "NA", "OC", "SA"}
MAX_LOOKUPS = 1_000_000
MAX_COMPRESSED_BYTES = 256 * 1024 * 1024
MAX_DATABASE_BYTES = 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
ATTRIBUTION = {
    "name": "DB-IP",
    "url": "https://db-ip.com",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
}


class Reader(Protocol):
    def get_with_prefix_len(self, ip_address: str) -> tuple[object, int]: ...


def _public_parts[N: (ipaddress.IPv4Network, ipaddress.IPv6Network)](network: N) -> list[N]:
    # Clip special-purpose ranges even when a database record spans public and private IPs.
    special = (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
        "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
        "203.0.113.0/24", "224.0.0.0/3",
    ) if network.version == 4 else (
        "2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20",
    )
    exceptions = (
        "192.0.0.9/32", "192.0.0.10/32",
    ) if network.version == 4 else (
        "2001:1::1/128", "2001:1::2/128", "2001:3::/32",
        "2001:4:112::/48", "2001:20::/28", "2001:30::/28",
    )
    network_type = type(network)
    parts = [network]
    if network.version == 6:
        unicast = network_type("2000::/3")
        if not network.overlaps(unicast):
            return []
        parts = [network if network.subnet_of(unicast) else unicast]
    exclusions = [network_type(value) for value in special]
    for value in exceptions:
        exception = network_type(value)
        exclusions = [
            part
            for excluded in exclusions
            for part in (
                excluded.address_exclude(exception)
                if exception.subnet_of(excluded) else [excluded]
            )
        ]
    for excluded in exclusions:
        parts = [
            part
            for candidate in parts
            for part in (
                [] if candidate.subnet_of(excluded)
                else candidate.address_exclude(excluded) if excluded.subnet_of(candidate)
                else [candidate]
            )
        ]
    return sorted(parts, key=lambda part: int(part.network_address))


def _location(record: object) -> dict[str, object] | None:
    if not isinstance(record, Mapping):
        return None
    location = record.get("location")
    continent = record.get("continent")
    if not isinstance(location, Mapping) or not isinstance(continent, Mapping):
        return None
    code = continent.get("code")
    if not isinstance(code, str) or code not in CONTINENTS:
        return None
    coordinates: dict[str, float] = {}
    for name, bound in (("latitude", 90), ("longitude", 180)):
        value = location.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not -bound <= value <= bound
            or not math.isfinite(value)
        ):
            return None
        coordinates[name] = float(value)

    def text(section: str, field: str) -> str | None:
        item = record.get(section)
        if not isinstance(item, Mapping):
            return None
        if field == "name":
            item = item.get("names")
            value = item.get("en") if isinstance(item, Mapping) else None
        else:
            value = item.get(field)
        return value.strip() if isinstance(value, str) and value.strip() else None

    return {
        **coordinates,
        "city": text("city", "name"),
        "country": text("country", "name"),
        "country_code": text("country", "iso_code"),
        "continent": code,
    }


def build_geolocation(
    index: Mapping[str, object],
    reader: Reader,
    database: str,
    *,
    max_lookups: int = MAX_LOOKUPS,
) -> dict[str, object]:
    rows = index.get("entries")
    if not isinstance(rows, list):
        raise ValueError("Search index must contain an entries array")
    networks: dict[str, Network] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("cidr"), str):
            raise ValueError("Every search index entry must have a CIDR")
        network = ipaddress.ip_network(row["cidr"], strict=False)
        networks.setdefault(str(network), network)
    entries: list[dict[str, object]] = []
    unlocated: list[str] = []
    lookups = 0
    for cidr, network in networks.items():
        located = False
        if isinstance(network, ipaddress.IPv4Network):
            public_parts: list[Network] = [*_public_parts(network)]
        else:
            public_parts = [*_public_parts(network)]
        for public in public_parts:
            address_type = type(public.network_address)
            cursor = int(public.network_address)
            last = int(public.broadcast_address)
            while cursor <= last:
                lookups += 1
                if lookups > max_lookups:
                    raise ValueError(
                        f"Geolocation exceeded {max_lookups} MMDB lookups at {cidr}; "
                        "increase --max-lookups to export complete coverage"
                    )
                address = address_type(cursor)
                record, prefix = reader.get_with_prefix_len(str(address))
                if not 0 <= prefix <= public.max_prefixlen:
                    raise ValueError(f"Invalid MMDB prefix length {prefix} for {address}")
                matched = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
                intersection = public if public.prefixlen >= matched.prefixlen else matched
                location = _location(record)
                if location is not None:
                    entries.append({"cidr": cidr, "network": str(intersection), **location})
                    located = True
                cursor = int(intersection.broadcast_address) + 1
        if not located:
            unlocated.append(cidr)
    return {
        "schema_version": "v1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "database": database,
        "attribution": dict(ATTRIBUTION),
        "entries": entries,
        "unlocated_cidrs": unlocated,
    }


@contextmanager
def downloaded_database(
    client: httpx.Client, directory: Path, *, today: date | None = None
) -> Iterator[tuple[Path, str]]:
    today = today or datetime.now(UTC).date()
    previous = today.replace(day=1) - timedelta(days=1)
    token = uuid4().hex
    compressed = directory / f".dbip-{token}.mmdb.gz"
    database = directory / f".dbip-{token}.mmdb"
    try:
        for month in (today, previous):
            filename = f"dbip-city-lite-{month:%Y-%m}.mmdb"
            url = f"https://download.db-ip.com/free/{filename}.gz"
            with client.stream("GET", url) as response:
                if response.status_code == 404 and month == today:
                    continue
                response.raise_for_status()
                size = 0
                with compressed.open("xb") as output:
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        size += len(chunk)
                        if size > MAX_COMPRESSED_BYTES:
                            raise ValueError("Compressed DB-IP database exceeds size limit")
                        output.write(chunk)
            size = 0
            with gzip.open(compressed, "rb") as source, database.open("xb") as output:
                while chunk := source.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > MAX_DATABASE_BYTES:
                        raise ValueError("DB-IP database exceeds decompressed size limit")
                    output.write(chunk)
            yield database, filename
            return
    finally:
        compressed.unlink(missing_ok=True)
        database.unlink(missing_ok=True)


def _write_geolocation(
    index_path: Path, output_path: Path, database: Path, name: str, max_lookups: int
) -> None:
    try:
        maxminddb = importlib.import_module("maxminddb")
    except ImportError as error:
        raise RuntimeError("Install the geolocation extra: pip install '.[geo]'") from error
    index = json.loads(index_path.read_text())
    if not isinstance(index, dict):
        raise ValueError("Search index must be a JSON object")
    with maxminddb.open_database(str(database)) as reader:
        result = build_geolocation(index, reader, name, max_lookups=max_lookups)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build DB-IP City Lite geolocation for the site")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path, help="Existing offline MMDB database")
    source.add_argument("--download", action="store_true", help="Download DB-IP City Lite")
    parser.add_argument("--max-lookups", type=int, default=MAX_LOOKUPS)
    args = parser.parse_args(argv)
    if args.max_lookups < 1:
        parser.error("--max-lookups must be positive")
    try:
        if args.database:
            _write_geolocation(
                args.index, args.output, args.database, args.database.name, args.max_lookups
            )
        else:
            with httpx.Client(
                timeout=httpx.Timeout(60, connect=10),
                follow_redirects=True,
                headers={"User-Agent": "public-ips-geolocation"},
            ) as client, downloaded_database(client, Path.cwd()) as (database, name):
                _write_geolocation(args.index, args.output, database, name, args.max_lookups)
    except (OSError, ValueError, RuntimeError, httpx.HTTPError) as error:
        parser.exit(1, f"Geolocation failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
