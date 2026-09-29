"""Load the TOML file that describes your wallets. Paths in it are relative to the file."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .currencies import notation_problem
from .model import DataError
from .timezones import get_zone

ADAPTERS = ("safetrade", "quantus", "universal")


@dataclass
class ManualFile:
    path: Path
    timezone: str


@dataclass
class WalletConfig:
    name: str
    adapter: str
    output: str
    options: dict[str, Any]
    manual_files: list[ManualFile] = field(default_factory=list)
    expected_balances: dict[str, Decimal] = field(default_factory=dict)  # asset key -> amount


@dataclass
class Config:
    path: Path
    timezone: str
    output_dir: Path
    utc_copy: bool
    assets: dict[str, str]  # asset key -> Koinly currency notation
    wallets: list[WalletConfig]
    evm: dict[str, Any] | None

    @property
    def base(self) -> Path:
        return self.path.parent

    def resolve(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.base / path

    def currency(self, asset: str) -> str:
        """Koinly notation of an asset key from [assets]; unknown keys are an error."""
        try:
            return self.assets[asset]
        except KeyError:
            raise DataError(f"asset {asset!r} is not listed in [assets]") from None


def _decimal(value: Any, where: str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise DataError(f"{where}: {value!r} is not a number") from None


def load(path: Path) -> Config:
    path = path.resolve()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise DataError(f"{path.name}: {error}") from None

    zone = str(raw.get("timezone", "UTC"))
    get_zone(zone)
    assets = {str(key): str(value) for key, value in raw.get("assets", {}).items()}
    for key, notation in assets.items():
        if problem := notation_problem(notation):
            raise DataError(f"[assets] {key}: {problem}")

    wallets = []
    names = set()
    for number, table in enumerate(raw.get("wallets", []), start=1):
        table = dict(table)
        where = f"[[wallets]] #{number}"
        name = str(table.pop("name", "")).strip()
        adapter = str(table.pop("adapter", "")).strip()
        output = str(table.pop("output", "")).strip()
        if not name or not output:
            raise DataError(f"{where}: 'name' and 'output' are required")
        if name in names:
            raise DataError(f"{where}: wallet name {name!r} is used twice")
        names.add(name)
        if adapter not in ADAPTERS:
            raise DataError(f"{where} ({name}): adapter must be one of {', '.join(ADAPTERS)}")
        manual = []
        for item in table.pop("manual_files", []):
            if "path" not in item or "timezone" not in item:
                raise DataError(f"{where} ({name}): each manual file needs 'path' and 'timezone'")
            get_zone(str(item["timezone"]))
            manual.append(ManualFile(Path(str(item["path"])), str(item["timezone"])))
        expected = {str(asset): _decimal(amount, f"{name} expected_balances.{asset}")
                    for asset, amount in table.pop("expected_balances", {}).items()}
        for asset in expected:
            if asset not in assets:
                raise DataError(f"{where} ({name}): expected_balances uses {asset!r}, which is not in [assets]")
        wallets.append(WalletConfig(name, adapter, output, table, manual, expected))
    if not wallets:
        raise DataError(f"{path.name}: no [[wallets]] defined")

    evm = raw.get("evm")
    if evm is not None:
        tokens = evm.get("tokens", {})
        if not tokens:
            raise DataError("[evm] needs at least one entry in [evm.tokens]")
        for contract, spec in tokens.items():
            if not isinstance(spec, dict) or str(spec.get("asset", "")) not in assets:
                raise DataError(f"[evm.tokens] {contract}: 'asset' must be a key from [assets]")
            if not isinstance(spec.get("decimals", 18), int):
                raise DataError(f"[evm.tokens] {contract}: 'decimals' must be a whole number")

    return Config(
        path=path,
        timezone=zone,
        output_dir=Path(str(raw.get("output_dir", "output"))),
        utc_copy=bool(raw.get("utc_copy", True)),
        assets=assets,
        wallets=wallets,
        evm=evm,
    )
