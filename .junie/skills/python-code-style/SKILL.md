---
name: python-code-style
description: Enforce Python coding standards for file operations, POSIX path formatting, strict type annotations, pre-compiled regex constants, typed data structures, unittest testing, error handling/logging, and code reuse. Use whenever writing, refactoring, or reviewing Python code or tests.
---

# Python Developer Code Style

Follow these standards strictly whenever generating, modifying, or reviewing Python code in this project.

## 1. File & Path Operations (`pathlib`)

* **Use `pathlib.Path` by default:** Always prefer `pathlib.Path` over `os.path`, `glob`, or built-in string path manipulation for
  reading, writing, checking existence, creating directories, and iterating over files.
* **Enforce POSIX path output:** Whenever outputting, serializing, logging, or formatting paths as strings (e.g., for APIs,
  configs, URLs, or cross-platform consistency), convert them using `PurePosixPath` or `.as_posix()`.
    * *Preferred:* `PurePosixPath(path).as_posix()` or `path.as_posix()`
    * *Avoid:* `str(path)` when generating external/serialized path outputs on Windows or mixed environments.

```python
from pathlib import Path, PurePosixPath


def get_normalized_config_path(base_dir: Path, filename: str) -> str:
    target = base_dir / "configs" / filename
    return PurePosixPath(target).as_posix()
```

## 2. Strict Type Annotations

* **Annotate all functions and methods:** Every newly created or modified function must include complete type annotations for
  **all arguments** and the **return value** (including `-> None` for procedures and test methods).
* Use modern built-in collection types (`list[...]`, `dict[...]`, `tuple[...]`, `set[...]`) and union syntax (`X | Y` or
  `X | None`) where supported by the project's Python version.

```python
def read_lines(file_path: Path, encoding: str = "utf-8") -> list[str]:
    return file_path.read_text(encoding=encoding).splitlines()
```

## 3. Typed Data Structures Over Raw Dictionaries

* **Avoid untyped `dict[str, Any]` for structured records:** Use explicit models so keys, types, and defaults are statically
  verifiable.
* **Choose the right structure:**
    * **`@dataclass(frozen=True, slots=True)` (or mutable `@dataclass`):** Default choice for internal domain objects, configs,
      and return models. Prefer `frozen=True` when mutation is not needed.
    * **`TypedDict`:** Use when modeling raw JSON payloads, external API responses, or dictionary contracts that must remain
      standard `dict` instances at runtime.
    * **`Enum` / `StrEnum`:** Use instead of raw magic strings or integer status codes for fixed sets of options.

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict


class RecordType(StrEnum):
    SOA = "SOA"
    A = "A"
    CNAME = "CNAME"


@dataclass(frozen=True, slots=True)
class DnsRecord:
    origin: str
    record_type: RecordType
    ttl: int = 3600


class RawZonePayload(TypedDict):
    zone_name: str
    records: list[str]
```

## 4. Pre-Compiled Regular Expressions

* **Use module-level compiled constants:** Never pass inline regex pattern strings directly into `re.search()`, `re.match()`,
  `re.findall()`, or `re.sub()`.
* Define patterns as `UPPER_SNAKE_CASE` constants using `re.compile(...)` at the module level (with flags included in
  `re.compile`) and reuse the compiled pattern object.

```python
import re

SOA_RECORD_PATTERN: re.Pattern[str] = re.compile(
    r"^(\S+)\s+IN\s+SOA\b", re.MULTILINE | re.IGNORECASE
)


# Avoid:
# soa_match = re.search(r'^(\S+)\s+IN\s+SOA\b', txt, re.M | re.IGNORECASE)

# Preferred:
def extract_soa_origin(zone_text: str) -> str | None:
    match = SOA_RECORD_PATTERN.search(zone_text)
    return match.group(1) if match else None
```

## 5. Error Handling & Logging

* **Use `logging` instead of `print()`:** Never use `print()` for diagnostics, status updates, or errors in application/library
  code. Initialize a module-level logger via `logger = logging.getLogger(__name__)`.
* **Use lazy `%`-formatting in log calls:** Pass arguments to logger methods (`logger.info("Reading %s", path.as_posix())`) rather
  than f-strings so string interpolation is skipped when the log level is disabled.
* **Catch specific exceptions and preserve tracebacks:**
    * Avoid bare `except:` or overly broad `except Exception:` blocks unless at a top-level boundary.
    * Use `logger.exception(...)` inside `except` blocks when logging caught errors so the full stack trace is preserved.
    * Chain re-raised exceptions using `raise NewError(...) from exc`.

```python
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_config_text(config_path: Path) -> str:
    try:
        return config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        logger.error("Configuration file not found: %s", config_path.as_posix())
        raise RuntimeError(f"Missing config: {config_path.as_posix()}") from exc
```

## 6. Testing (`unittest`)

* **Prefer `unittest` over third-party frameworks:** When creating or updating tests, use Python's standard library `unittest`
  module (`unittest.TestCase`, `unittest.mock`, `setUp`/`tearDown`) rather than `pytest` fixtures or bare `assert` statements,
  unless the existing test suite strictly requires otherwise.
* Include return type annotations (`-> None`) on all test methods and `setUp`/`tearDown` hooks.

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestConfigPath(unittest.TestCase):
    def test_normalized_path_returns_posix_format(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            result = get_normalized_config_path(Path(tmp_dir), "app.json")
            self.assertTrue(result.endswith("/configs/app.json"))
```

## 7. Code Reuse & DRY Principle

* **Analyze before writing:** Before implementing a new function, helper, or class, search the existing codebase for similar
  logic, utilities, or base classes.
* **Reuse or generalize:**
    * If an exact match exists, import and call it directly.
    * If nearly identical logic exists, refactor the existing function (e.g., by adding an optional parameter or extracting a
      shared helper) rather than duplicating code with minor variations.

## Checklist Before Finishing

- [ ] Are all file system operations using `pathlib.Path`?
- [ ] Are all output/serialized path strings formatted via `PurePosixPath` / `.as_posix()`?
- [ ] Do all functions and test methods have complete argument and return type annotations?
- [ ] Are structured records modeled with `dataclasses`, `TypedDict`, or `Enum` instead of raw `dict[str, Any]`?
- [ ] Are all regular expressions defined as pre-compiled `re.compile(...)` constants rather than inline strings?
- [ ] Are errors handled with specific exceptions (`raise ... from exc`) and logged via `logging.getLogger(__name__)` without
  `print()`?
- [ ] Are new tests written using standard library `unittest`?
- [ ] Was the codebase checked to reuse or extend existing functions instead of duplicating logic?
