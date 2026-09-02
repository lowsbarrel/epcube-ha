"""`epcube` - a command line over the client.

    uv run epcube status          live state, one screen
    uv run epcube login --save    mint a token and store it in .env
    uv run epcube series          today's curve
    uv run epcube pv              per-string solar telemetry
    uv run epcube routes          the discovered API surface and its coverage
    uv run epcube probe <path>    call an unmodelled route

Configuration resolves command line, then environment, then `.env`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .client import EpCubeAsyncClient
from .const import Region, Scope
from .exceptions import EpCubeError
from .registry import Verified, by_group, coverage
from .transport import redact

ENV_FILE = Path(".env")


# --- configuration ---------------------------------------------------------


def load_env() -> dict[str, str]:
    """Read `.env` without taking a dependency on a dotenv library."""
    if not ENV_FILE.is_file():
        return {}
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def setting(name: str, cli: str | None, env: dict[str, str], default: str = "") -> str:
    return cli or os.environ.get(name) or env.get(name) or default


def save_token(token: str) -> Path:
    """Replace EPCUBE_TOKEN in `.env`, preserving everything else."""
    lines = []
    if ENV_FILE.is_file():
        lines = [
            line
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("EPCUBE_TOKEN=")
        ]
    lines.append(f'EPCUBE_TOKEN="{token}"')
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ENV_FILE


def build_client(args: argparse.Namespace, env: dict[str, str]) -> EpCubeAsyncClient:
    return EpCubeAsyncClient(
        region=Region.parse(setting("EPCUBE_REGION", args.region, env, "EU")),
        token=setting("EPCUBE_TOKEN", args.token, env) or None,
    )


# --- output ----------------------------------------------------------------


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def row(label: str, value: Any) -> None:
    print(f"  {label:<30} {value}")


def dump(model: Any) -> Any:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model


# --- commands --------------------------------------------------------------


async def cmd_status(args: argparse.Namespace, env: dict[str, str]) -> int:
    async with build_client(args, env) as client:
        snap = await client.snapshot(
            setting("EPCUBE_SN", args.sn, env) or None,
            include_series=not args.no_series,
            include_outages=True,
        )
        if args.json:
            emit(dump(snap))
            return 0

        live, mode = snap.live, snap.mode
        print(f"\nEP Cube {snap.dev_id}  ({client.region.value})")
        print(f"  {snap.summary_line()}\n")

        row("battery", f"{snap.battery_soc}%  ({live.battery_current_electricity} kWh)")
        if snap.battery_power_w is not None:
            source = "measured" if snap.series else "derived"
            row("battery power", f"{snap.battery_power_w:+.0f} W  ({source})")
        row("solar", f"{live.solar_power} W")
        row("grid", f"{live.grid_power} W")
        row("house load", f"{live.load_power} W")
        if mode and mode.mode:
            row("mode", mode.mode.label)
            row("reserve (self-cons.)", f"{mode.self_consumption_reserve_soc}%")
            row("reserve (backup)", f"{mode.backup_power_reserve_soc}%")
            row("grid charging", "allowed" if mode.grid_charging_allowed else "blocked")
            row("tou schedule", "configured" if mode.has_tou_schedule else "empty")
        if snap.detail:
            row("model", snap.detail.model_type)
        if snap.pv and snap.pv.active:
            for string in snap.pv.active:
                row(
                    f"pv string {string.index}",
                    f"{string.voltage} V  {string.current} A  {string.power_w:.0f} W",
                )
        if snap.network:
            row("wifi", f"{snap.network.wifi_name}  (level {snap.network.signal_level})")
        if snap.today:
            row("today", f"solar {snap.today.solar_electricity} kWh")
        if snap.outages:
            row("outages logged", len(snap.outages))
            for event in snap.outages[:3]:
                row("  ", f"{event.start_time} → {event.end_time} ({event.duration})")
        if snap.errors:
            print("\n  degraded sections:")
            for name, error in snap.errors.items():
                row(f"  {name}", error[:70])
        print()
        return 0


async def cmd_series(args: argparse.Namespace, env: dict[str, str]) -> int:
    async with build_client(args, env) as client:
        _, dev_id, _ = await client.resolve_device(setting("EPCUBE_SN", args.sn, env) or None)
        scope = Scope[args.scope.upper()]
        when = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
        series = await client.data.series(dev_id, scope, when)

        if args.json:
            emit(dump(series))
            return 0

        populated = series.populated()
        print(
            f"\n{scope.name.lower()} series for {when}: {len(series)} points "
            f"({len(populated)} with data), one per {series.granularity}\n"
        )
        field = args.field
        for when_, value in series.timeline(field)[-args.tail :]:
            bar = "█" * min(40, int(abs(value) / 50)) if "_w" in field else ""
            print(f"  {when_:%Y-%m-%d %H:%M}  {value:>10.2f}  {bar}")
        print()
        return 0


async def cmd_pv(args: argparse.Namespace, env: dict[str, str]) -> int:
    async with build_client(args, env) as client:
        _, dev_id, _ = await client.resolve_device(setting("EPCUBE_SN", args.sn, env) or None)
        pv = await client.device.pv_strings(dev_id)
        if args.json:
            emit(dump(pv))
            return 0
        print()
        for string in pv.strings:
            state = "active" if string.is_active else "idle"
            row(
                f"PV{string.index} ({state})",
                f"{string.voltage or 0:>7.2f} V  {string.current or 0:>5.2f} A  "
                f"{string.power_w or 0:>7.0f} W",
            )
        row("total", f"{pv.total_power_w:.0f} W")
        print()
        return 0


async def cmd_login(args: argparse.Namespace, env: dict[str, str]) -> int:
    email = setting("EPCUBE_EMAIL", args.email, env)
    password = setting("EPCUBE_PASSWORD", args.password, env)
    if not email or not password:
        print("need an email and password: pass --email/--password or set them in .env")
        return 1

    async with build_client(args, env) as client:
        from .auth import async_login

        print(f"signing in to {client.base_url} as {email}")
        token = await async_login(
            client,
            email,
            password,
            attempts=args.attempts,
            on_attempt=lambda msg: print(f"  {msg}"),
        )
        print(f"\ntoken: {redact(token)}")
        if args.save:
            print(f"saved to {save_token(token)}")
        else:
            print(token)
        return 0


async def cmd_probe(args: argparse.Namespace, env: dict[str, str]) -> int:
    params = dict(p.split("=", 1) for p in args.param)
    async with build_client(args, env) as client:
        ok, payload = await client.probe(args.path, **params)
        print(f"{'OK  ' if ok else 'FAIL'} {args.path}")
        emit(payload)
        return 0 if ok else 1


def cmd_routes(args: argparse.Namespace, _: dict[str, str]) -> int:
    stats = coverage()
    print(
        f"\n{stats['total']} routes discovered in the app  ·  "
        f"{stats['wrapped']} wrapped  ·  {stats['verified']} verified against a real system\n"
    )
    marks = {
        Verified.WORKING: "ok  ",
        Verified.REJECTED: "500 ",
        Verified.ABSENT: "404 ",
        Verified.UNTESTED: "    ",
    }
    for group, routes in sorted(by_group().items()):
        if args.group and group != args.group:
            continue
        print(f"{group}/  ({len(routes)})")
        for route in routes:
            if args.wrapped and not route.wrapped:
                continue
            wrapper = f"client.{route.wrapper}" if route.wrapper else ""
            note = f"  ({route.note})" if route.note else ""
            print(f"  {marks[route.verified]} {route.path:<44} {wrapper}{note}")
        print()
    return 0


# --- entry point -----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="epcube", description=__doc__.splitlines()[0])
    parser.add_argument("--region", choices=[r.value for r in Region])
    parser.add_argument("--token")
    parser.add_argument("--sn", help="plant serial; read from the account if omitted")
    parser.add_argument("--json", action="store_true", help="raw JSON instead of a report")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="live state, one screen")
    status.add_argument("--no-series", action="store_true", help="skip the time series")
    status.set_defaults(func=cmd_status)

    series = sub.add_parser("series", help="energy curve over a window")
    series.add_argument("--scope", default="day", choices=[s.name.lower() for s in Scope])
    series.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    series.add_argument(
        "--field", default="battery_power_w", help="reading to plot (default: battery_power_w)"
    )
    series.add_argument("--tail", type=int, default=24, help="how many points to show")
    series.set_defaults(func=cmd_series)

    pv = sub.add_parser("pv", help="per-string solar telemetry")
    pv.set_defaults(func=cmd_pv)

    login = sub.add_parser("login", help="mint a Bearer token")
    login.add_argument("--email")
    login.add_argument("--password")
    login.add_argument("--attempts", type=int, default=5)
    login.add_argument("--save", action="store_true", help="write the token to .env")
    login.set_defaults(func=cmd_login)

    probe = sub.add_parser("probe", help="call a route that has no wrapper yet")
    probe.add_argument("path", help="e.g. device/getAssetData")
    probe.add_argument("--param", action="append", default=[], metavar="K=V")
    probe.set_defaults(func=cmd_probe)

    routes = sub.add_parser("routes", help="the discovered API surface")
    routes.add_argument("--group", help="only this prefix, e.g. device")
    routes.add_argument("--wrapped", action="store_true", help="only routes with a wrapper")
    routes.set_defaults(func=cmd_routes)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = load_env()
    try:
        if asyncio.iscoroutinefunction(args.func):
            return asyncio.run(args.func(args, env))
        return args.func(args, env)
    except EpCubeError as exc:
        print(f"\nerror: {exc}\n")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
