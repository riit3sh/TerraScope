"""Validate a ParcelRecord object or an array of ParcelRecord objects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = Path(__file__).with_name("parcel_schema.json")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"File not found: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from None


def validate_file(path: Path) -> list[str]:
    schema = load_json(SCHEMA_PATH)
    payload = load_json(path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    records = payload if isinstance(payload, list) else [payload]
    errors: list[str] = []

    if not records:
        errors.append("document: expected one ParcelRecord object or a non-empty array")
        return errors

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record {index + 1}: expected an object")
            continue
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "root"
            errors.append(f"record {index + 1} ({location}): {error.message}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate TerraScope ParcelRecord JSON.")
    parser.add_argument("file", type=Path, help="JSON file containing one record or an array of records")
    args = parser.parse_args()

    try:
        payload = load_json(args.file)
        errors = validate_file(args.file)
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    if errors:
        print(f"FAIL: {args.file} has {len(errors)} validation error(s).", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    record_count = len(payload) if isinstance(payload, list) else 1
    print(f"PASS: {args.file} is valid ({record_count} ParcelRecord object(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
