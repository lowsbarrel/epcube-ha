"""The CLI, driven end to end against the canned API.

`epcube_api.cli` reads `.env` from the working directory, which in this repo
holds a real token. Every test here redirects ENV_FILE at a temp file and
injects a MockTransport client, so nothing can reach the network.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import httpx
import pytest

from epcube_api import cli
from epcube_api.client import EpCubeAsyncClient

from .conftest import SN, Recorder


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No real .env, no inherited EPCUBE_* variables."""
    monkeypatch.setattr(cli, "ENV_FILE", tmp_path / ".env")
    for name in (
        "EPCUBE_TOKEN",
        "EPCUBE_EMAIL",
        "EPCUBE_PASSWORD",
        "EPCUBE_REGION",
        "EPCUBE_SN",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / ".env"


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch, recorder: Recorder):
    """Point the CLI's client factory at the canned transport."""

    def factory(**kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
        return EpCubeAsyncClient(**kwargs)

    monkeypatch.setattr(cli, "EpCubeAsyncClient", factory)
    return recorder


def run(*argv: str) -> int:
    return cli.main(list(argv))


# --- configuration ---------------------------------------------------------


def test_load_env_parses_and_ignores_noise(isolated_env: Path):
    isolated_env.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                'EPCUBE_TOKEN="quoted"',
                "EPCUBE_REGION=EU",
                "not a pair",
                "EPCUBE_SN='single'",
            ]
        ),
        encoding="utf-8",
    )
    values = cli.load_env()
    assert values == {
        "EPCUBE_TOKEN": "quoted",
        "EPCUBE_REGION": "EU",
        "EPCUBE_SN": "single",
    }


def test_load_env_without_a_file():
    assert cli.load_env() == {}


def test_setting_precedence(monkeypatch: pytest.MonkeyPatch):
    env = {"KEY": "from-dotenv"}
    assert cli.setting("KEY", "from-cli", env) == "from-cli"
    assert cli.setting("KEY", None, env) == "from-dotenv"
    monkeypatch.setenv("KEY", "from-environ")
    assert cli.setting("KEY", None, env) == "from-environ"
    assert cli.setting("MISSING", None, {}, "fallback") == "fallback"


def test_save_token_replaces_only_the_token_line(isolated_env: Path):
    isolated_env.write_text("EPCUBE_REGION=EU\nEPCUBE_TOKEN=old\nEPCUBE_SN=123\n", encoding="utf-8")
    cli.save_token("new")
    written = isolated_env.read_text(encoding="utf-8")
    assert 'EPCUBE_TOKEN="new"' in written
    assert "EPCUBE_TOKEN=old" not in written
    assert "EPCUBE_REGION=EU" in written
    assert "EPCUBE_SN=123" in written


def test_save_token_creates_the_file(isolated_env: Path):
    cli.save_token("fresh")
    assert 'EPCUBE_TOKEN="fresh"' in isolated_env.read_text(encoding="utf-8")


# --- status ----------------------------------------------------------------


def test_status(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "--sn", SN, "status") == 0
    out = capsys.readouterr().out
    assert "EP Cube" in out
    assert "battery" in out
    assert "pv string 1" in out
    assert "wifi" in out
    assert "outages logged" in out


def test_status_reports_the_solar_source_consistently(wired, capsys):
    """The summary line and the detail row must not disagree."""
    assert run("--token", "t", "--sn", SN, "status") == 0
    out = capsys.readouterr().out
    summary = next(line for line in out.splitlines() if "SoC" in line)
    detail = next(line for line in out.splitlines() if line.strip().startswith("solar "))
    assert "610" in summary  # from the series, not live.solar_power (51)
    assert "610" in detail
    assert "(series)" in detail


def test_status_as_json(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "--sn", SN, "--json", "status") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dev_id"]
    assert payload["live"]["battery_soc"] == 86


def test_status_without_the_series(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "--sn", SN, "status", "--no-series") == 0
    out = capsys.readouterr().out
    assert "(derived)" in out


def test_status_reports_degraded_sections(monkeypatch, recorder: Recorder, capsys):
    recorder.overrides["device/netWorkInfo"] = httpx.Response(500, json={"message": "no"})

    def factory(**kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
        kwargs["max_retries"] = 1
        return EpCubeAsyncClient(**kwargs)

    monkeypatch.setattr(cli, "EpCubeAsyncClient", factory)
    assert run("--token", "t", "--sn", SN, "status") == 0
    assert "degraded sections" in capsys.readouterr().out


# --- series ----------------------------------------------------------------


def test_series(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "--sn", SN, "series") == 0
    out = capsys.readouterr().out
    assert "day series" in out
    assert "five minutes" in out


def test_series_with_an_explicit_date_and_scope(wired, capsys):
    assert (
        run("--token", "t", "--sn", SN, "series", "--scope", "month", "--date", "2026-09-02") == 0
    )
    assert "month series" in capsys.readouterr().out


def test_series_as_json(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "--sn", SN, "--json", "series") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == 1
    assert payload["points"]


def test_series_with_a_non_watt_field_draws_no_bars(wired, capsys):
    assert run("--token", "t", "--sn", SN, "series", "--field", "battery_soc") == 0
    assert "█" not in capsys.readouterr().out


# --- pv --------------------------------------------------------------------


def test_pv(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "--sn", SN, "pv") == 0
    out = capsys.readouterr().out
    assert "PV1 (active)" in out
    assert "PV3 (idle)" in out
    assert "total" in out


def test_pv_as_json(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "--sn", SN, "--json", "pv") == 0
    assert len(json.loads(capsys.readouterr().out)["strings"]) == 4


# --- probe -----------------------------------------------------------------


def test_probe_success(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "probe", "device/netWorkInfo", "--param", "devId=4953") == 0
    assert "OK" in capsys.readouterr().out


def test_probe_failure_exits_nonzero(wired, capsys: pytest.CaptureFixture[str]):
    assert run("--token", "t", "probe", "device/nope") == 1
    assert "FAIL" in capsys.readouterr().out


# --- routes ----------------------------------------------------------------


def test_routes_lists_the_surface(capsys: pytest.CaptureFixture[str]):
    assert run("routes") == 0
    out = capsys.readouterr().out
    assert "routes discovered in the app" in out
    assert "device/homeDeviceInfo" in out
    assert "client.device.home_info" in out


def test_routes_can_filter(capsys: pytest.CaptureFixture[str]):
    assert run("routes", "--group", "vpp", "--wrapped") == 0
    out = capsys.readouterr().out
    assert "vpp/" in out
    assert "device/homeDeviceInfo" not in out


# --- login -----------------------------------------------------------------


def test_login_without_credentials(capsys: pytest.CaptureFixture[str]):
    assert run("login") == 1
    assert "need an email and password" in capsys.readouterr().out


def test_login_saves_the_token(monkeypatch, isolated_env: Path, capsys):
    from .test_auth import Login

    script = Login()

    def factory(**kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(script.handler))
        return EpCubeAsyncClient(**kwargs)

    monkeypatch.setattr(cli, "EpCubeAsyncClient", factory)
    assert run("login", "--email", "a@b.c", "--password", "pw", "--save") == 0
    out = capsys.readouterr().out
    assert "signing in" in out
    assert "saved to" in out
    assert 'EPCUBE_TOKEN="issued-token"' in isolated_env.read_text(encoding="utf-8")


def test_login_prints_the_token_when_not_saving(monkeypatch, capsys):
    from .test_auth import Login

    script = Login()

    def factory(**kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(script.handler))
        return EpCubeAsyncClient(**kwargs)

    monkeypatch.setattr(cli, "EpCubeAsyncClient", factory)
    assert run("login", "--email", "a@b.c", "--password", "pw") == 0
    assert "issued-token" in capsys.readouterr().out


# --- top level -------------------------------------------------------------


def test_an_api_error_becomes_exit_1(monkeypatch, recorder: Recorder, capsys):
    recorder.overrides["user/user/base"] = httpx.Response(401, json={"message": "stale"})

    def factory(**kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
        return EpCubeAsyncClient(**kwargs)

    monkeypatch.setattr(cli, "EpCubeAsyncClient", factory)
    assert run("--token", "stale", "status") == 1
    assert "error:" in capsys.readouterr().out


def test_an_interrupt_becomes_exit_130(monkeypatch):
    def boom(argv=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "load_env", boom)
    assert cli.main(["routes"]) == 130


def test_output_is_utf8_even_on_a_windows_pipe(monkeypatch):
    """A redirected stdout on Windows is cp1252, which cannot encode the ·, →
    and █ the reports use; main() switches it to UTF-8 before printing."""
    pipe = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", pipe)
    assert cli.main(["routes"]) == 0
    pipe.flush()
    assert pipe.encoding == "utf-8"
    assert "·" in pipe.buffer.getvalue().decode("utf-8")


def test_a_stream_without_reconfigure_is_left_alone(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert cli.main(["routes"]) == 0


def test_no_command_is_a_usage_error():
    with pytest.raises(SystemExit):
        cli.main([])


def test_module_entry_point_is_wired():
    """`python -m epcube_api.cli` and the console script share one main()."""
    assert callable(cli.main)
    assert cli.build_parser().prog == "epcube"


def test_status_with_every_optional_section_missing(monkeypatch, recorder: Recorder, capsys):
    """A device reporting almost nothing must still print a usable screen.

    Every supplementary read fails and the live body carries only an id, so each
    conditional row in the report takes its other branch.
    """
    for route in (
        "device/getSwitchMode",
        "device/userDeviceInfo",
        "device/getSolarPvPower",
        "device/netWorkInfo",
        "device/queryDataElectricityV2",
        "device/getDevPowerCutLog",
        "device/deviceList",
        "device/queryDataGraphV2",
    ):
        recorder.overrides[route] = httpx.Response(500, json={"message": "down"})
    recorder.overrides["device/homeDeviceInfo"] = httpx.Response(
        200, json={"status": 200, "data": {"devId": "4953"}}
    )

    def factory(**kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
        kwargs["max_retries"] = 1
        return EpCubeAsyncClient(**kwargs)

    monkeypatch.setattr(cli, "EpCubeAsyncClient", factory)
    assert run("--token", "t", "--sn", SN, "status") == 0

    out = capsys.readouterr().out
    assert "EP Cube 4953" in out
    assert "degraded sections" in out

    # Check the report body only: the failed section names appear again in the
    # degraded list below it, which is the point of that list.
    report = out.split("degraded sections")[0]
    for absent in ("battery power", "solar ", "mode ", "model", "pv string", "wifi", "today"):
        assert absent not in report
