#!/usr/bin/env python3
"""Helpers to load shared protocol constants for Python tooling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _constants_path() -> Path:
    return Path(__file__).resolve().parent / "constants.json"


def load_constants() -> dict[str, Any]:
    with _constants_path().open("r", encoding="utf-8") as fp:
        return json.load(fp)

