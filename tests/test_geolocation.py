from __future__ import annotations

import gzip
import ipaddress
import json
import shutil
import sys
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from public_ips import geolocation

LOCATION = {
    "location": {"latitude": 37.7749, "longitude": -122.4194},
    "city": {"names": {"en": "San Francisco"}},
    "country": {"names": {"en": "United States"}, "iso_code": "US"},
    "continent": {"code": "NA"},
}


class FakeReader:
    def __init__(self, records: dict[str, object]) -> None:
        self.records = {ipaddress.ip_network(cidr): record for cidr, record in records.items()}
        self.calls: list[str] = []

    def get_with_prefix_len(self, ip_address: str) -> tuple[object, int]:
        self.calls.append(ip_address)
        address = ipaddress.ip_address(ip_address)
        candidates = [net for net in self.records if address in net]
        if not candidates:
            return None, address.max_prefixlen
        matched = max(candidates, key=lambda net: net.prefixlen)
        terminal = matched
        # An MMDB terminal cannot straddle a more-specific record elsewhere in the trie.
        while any(
            net.version == terminal.version and net != terminal and net.subnet_of(terminal)
            for net in self.records
        ):
            terminal = next(net for net in terminal.subnets() if address in net)
        return self.records[matched], terminal.prefixlen

    def __enter__(self) -> FakeReader:
        return self

    def __exit__(self, *_: object) -> None:
        pass


@pytest.fixture
def workdir() -> Iterator[Path]:
    path = Path.cwd() / f".test-geolocation-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def export(reader: FakeReader, *cidrs: str, **kwargs: int) -> dict[str, object]:
    return geolocation.build_geolocation(
        {"entries": [{"cidr": cidr} for cidr in cidrs]}, reader, "test.mmdb", **kwargs
    )


def test_partitions_overlapping_records_and_published_networks() -> None:
    other = {**LOCATION, "location": {"latitude": 51.5, "longitude": -0.1}}
    reader = FakeReader({"8.8.8.0/24": LOCATION, "8.8.8.64/26": other})
    result = export(reader, "8.8.8.0/24", "8.8.8.64/27")
    entries = result["entries"]
    assert isinstance(entries, list)
    assert [(entry["cidr"], entry["network"]) for entry in entries] == [
        ("8.8.8.0/24", "8.8.8.0/26"),
        ("8.8.8.0/24", "8.8.8.64/26"),
        ("8.8.8.0/24", "8.8.8.128/25"),
        ("8.8.8.64/27", "8.8.8.64/27"),
    ]
    assert [entry["latitude"] for entry in entries] == [37.7749, 51.5, 37.7749, 51.5]
    assert reader.calls == ["8.8.8.0", "8.8.8.64", "8.8.8.128", "8.8.8.64"]
    assert result["unlocated_cidrs"] == []


def test_ipv6_unknown_prefix_stepping_and_host_boundaries() -> None:
    reader = FakeReader({
        "2606:4700::/126": None,
        "2606:4700::2/127": LOCATION,
        "2606:4700::3/128": {**LOCATION, "location": {"latitude": -90, "longitude": 180}},
    })
    result = export(reader, "2606:4700::/126", "2606:4700::3/128")
    entries = result["entries"]
    assert isinstance(entries, list)
    assert [entry["network"] for entry in entries] == [
        "2606:4700::2/128", "2606:4700::3/128", "2606:4700::3/128",
    ]
    assert reader.calls == ["2606:4700::", "2606:4700::2", "2606:4700::3", "2606:4700::3"]
    assert entries[1]["latitude"] == -90
    assert entries[1]["longitude"] == 180


def test_normalizes_and_deduplicates_cidrs() -> None:
    reader = FakeReader({"8.8.8.0/24": LOCATION, "2606:4700::/32": LOCATION})
    result = export(
        reader, "8.8.8.1/24", "8.8.8.0/24", "8.8.8.0/24",
        "2606:4700::/32", "2606:4700:0000::/32",
    )
    assert reader.calls == ["8.8.8.0", "2606:4700::"]
    entries = result["entries"]
    assert isinstance(entries, list)
    assert [entry["cidr"] for entry in entries] == ["8.8.8.0/24", "2606:4700::/32"]


@pytest.mark.parametrize("record", [
    None, {}, [], {"location": {}},
    {**LOCATION, "continent": {"code": "XX"}},
    {**LOCATION, "continent": {"code": ["NA"]}},
    {**LOCATION, "location": {"latitude": 91, "longitude": 0}},
    {**LOCATION, "location": {"latitude": 0, "longitude": -181}},
    {**LOCATION, "location": {"latitude": float("nan"), "longitude": 0}},
    {**LOCATION, "location": {"latitude": 0, "longitude": float("inf")}},
    {**LOCATION, "location": {"latitude": True, "longitude": 0}},
    {**LOCATION, "location": {"latitude": "37", "longitude": 0}},
    {**LOCATION, "location": {"latitude": 10**400, "longitude": 0}},
])
def test_unknown_and_invalid_locations_are_not_guessed(record: object) -> None:
    result = export(FakeReader({"8.8.8.0/24": record}), "8.8.8.0/24", "8.8.8.0/24")
    assert result["entries"] == []
    assert result["unlocated_cidrs"] == ["8.8.8.0/24"]


def test_optional_names_and_exact_json_contract() -> None:
    reader = FakeReader({"8.8.8.8/32": {
        "location": {"latitude": 0, "longitude": 0},
        "continent": {"code": "AN"},
    }})
    result = export(reader, "8.8.8.8/32")
    assert set(result) == {
        "schema_version", "generated_at", "database", "attribution", "entries", "unlocated_cidrs",
    }
    assert result["schema_version"] == "v1"
    assert result["database"] == "test.mmdb"
    assert datetime.fromisoformat(str(result["generated_at"])).tzinfo is not None
    assert result["attribution"] == geolocation.ATTRIBUTION
    assert result["entries"] == [{
        "cidr": "8.8.8.8/32", "network": "8.8.8.8/32", "latitude": 0.0, "longitude": 0.0,
        "city": None, "country": None, "country_code": None, "continent": "AN",
    }]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("cidr", [
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.1/32", "169.254.0.0/16",
    "172.16.0.0/12", "192.168.0.0/16", "192.0.2.0/24", "198.51.100.0/24",
    "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
    "::/128", "::1/128", "::ffff:8.8.8.8/128", "fc00::/7", "fe80::/10", "ff00::/8",
    "2001:db8::/32", "3fff::/20",
])
def test_skips_nonpublic_addresses_without_lookup(cidr: str) -> None:
    reader = FakeReader({cidr: LOCATION})
    result = export(reader, cidr)
    assert result["entries"] == []
    assert result["unlocated_cidrs"] == [str(ipaddress.ip_network(cidr))]
    assert not reader.calls


def test_broad_record_clips_private_intersections() -> None:
    reader = FakeReader({"8.0.0.0/6": LOCATION})
    result = export(reader, "8.0.0.0/6")
    entries = result["entries"]
    assert isinstance(entries, list)
    assert [entry["network"] for entry in entries] == ["8.0.0.0/7", "11.0.0.0/8"]


@pytest.mark.parametrize("cidr", ["192.0.0.9/32", "192.0.0.10/32", "2001:3::/32"])
def test_public_special_purpose_exceptions_are_preserved(cidr: str) -> None:
    result = export(FakeReader({cidr: LOCATION}), cidr)
    assert result["unlocated_cidrs"] == []


def test_expansion_limit_fails_instead_of_truncating() -> None:
    reader = FakeReader({"8.8.8.0/31": LOCATION, "8.8.8.2/31": LOCATION})
    with pytest.raises(ValueError, match="exceeded 1 MMDB lookups"):
        export(reader, "8.8.8.0/30", max_lookups=1)


@pytest.mark.parametrize("index", [{}, {"entries": None}, {"entries": [{}]},
                                  {"entries": [{"cidr": "invalid"}]}])
def test_invalid_index_is_rejected(index: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        geolocation.build_geolocation(index, FakeReader({}), "test.mmdb")


def test_invalid_database_prefix_is_rejected() -> None:
    class InvalidReader:
        def get_with_prefix_len(self, _: str) -> tuple[object, int]:
            return LOCATION, 33

    with pytest.raises(ValueError, match="Invalid MMDB prefix"):
        geolocation.build_geolocation(
            {"entries": [{"cidr": "8.8.8.8/32"}]}, InvalidReader(), "test.mmdb"
        )


def test_download_falls_back_on_404_across_year_boundary(workdir: Path) -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "2026-01" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=gzip.compress(b"database"))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with geolocation.downloaded_database(
            client, workdir, today=date(2026, 1, 1)
        ) as (path, name):
            assert path.read_bytes() == b"database"
            assert name == "dbip-city-lite-2025-12.mmdb"
            assert path.parent == workdir
    assert calls == [
        "https://download.db-ip.com/free/dbip-city-lite-2026-01.mmdb.gz",
        "https://download.db-ip.com/free/dbip-city-lite-2025-12.mmdb.gz",
    ]
    assert list(workdir.iterdir()) == []


@pytest.mark.parametrize("status", [403, 429, 500])
def test_download_does_not_fallback_for_other_errors(workdir: Path, status: int) -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            with geolocation.downloaded_database(client, workdir):
                pytest.fail("Download should fail")
    assert len(calls) == 1
    assert list(workdir.iterdir()) == []


@pytest.mark.parametrize("limit", ["MAX_COMPRESSED_BYTES", "MAX_DATABASE_BYTES"])
def test_download_size_limits_and_cleanup(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    monkeypatch.setattr(geolocation, limit, 2)
    with httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=gzip.compress(b"large database"))
    )) as client:
        with pytest.raises(ValueError, match="size limit"):
            with geolocation.downloaded_database(client, workdir):
                pytest.fail("Download should fail")
    assert list(workdir.iterdir()) == []


def test_invalid_gzip_cleans_up(workdir: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=b"not gzip")
    )) as client:
        with pytest.raises(gzip.BadGzipFile):
            with geolocation.downloaded_database(client, workdir):
                pytest.fail("Download should fail")
    assert list(workdir.iterdir()) == []


def test_offline_cli_writes_site_contract(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = FakeReader({"8.8.8.0/24": LOCATION})
    opened: list[str] = []

    def open_database(path: str) -> FakeReader:
        opened.append(path)
        return reader

    monkeypatch.setitem(sys.modules, "maxminddb", SimpleNamespace(open_database=open_database))
    index = workdir / "index.json"
    index.write_text(json.dumps({"entries": [{"cidr": "8.8.8.0/24"}]}))
    output = workdir / "dist" / "geolocation.json"
    database = workdir / "offline.mmdb"
    assert geolocation.main([
        "--index", str(index), "--output", str(output), "--database", str(database),
    ]) == 0
    result = json.loads(output.read_text())
    assert opened == [str(database)]
    assert result["database"] == "offline.mmdb"
    assert result["entries"][0]["city"] == "San Francisco"
    assert result["entries"][0]["country_code"] == "US"


def test_failed_export_does_not_replace_output(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = FakeReader({"8.8.8.0/31": LOCATION, "8.8.8.2/31": LOCATION})
    monkeypatch.setitem(
        sys.modules, "maxminddb", SimpleNamespace(open_database=lambda _: reader)
    )
    index = workdir / "index.json"
    index.write_text(json.dumps({"entries": [{"cidr": "8.8.8.0/30"}]}))
    output = workdir / "geolocation.json"
    output.write_text("existing artifact")
    with pytest.raises(SystemExit, match="1"):
        geolocation.main([
            "--index", str(index), "--output", str(output),
            "--database", "offline.mmdb", "--max-lookups", "1",
        ])
    assert output.read_text() == "existing artifact"
