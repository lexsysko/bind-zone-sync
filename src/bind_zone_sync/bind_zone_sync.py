#!/usr/bin/env python3
"""bind-zone-sync gen | restore

gen      write a secondary-zone config from a primary-zone config
restore  convert a secondary-zone config back to a primary-zone config
"""

import argparse
import ipaddress
import logging
import re
from pathlib import Path, PurePosixPath

logger = logging.getLogger("bind-zone-sync")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Manage BIND zones configuration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("command", choices=["gen", "restore"],
                   help="gen = write secondary-zone config; restore = convert secondary config back to primary")

    p.add_argument("--conf", default="/usr/local/etc/namedb/zones-primary.conf.auto",
                   help="Input zone config file (default: %(default)s)")
    p.add_argument("--out", default="/usr/local/etc/namedb/zones-secondary.conf.auto",
                   help="Output zone config file (default: %(default)s)")
    p.add_argument("--primaries", default="10.0.0.100;",
                   help="Full content for the primaries directive in generated secondary config (default: %(default)s)")
    p.add_argument("--db-path-find", default="/usr/local/etc/namedb/primary/",
                   help="Path prefix in zone file paths to replace (default: %(default)s)")
    p.add_argument("--db-path-replace", default="",
                   help="Replacement path prefix for secondary zone files; empty = keep original (default: keep)")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                   help="Logging level (default: %(default)s)")

    return p.parse_args()


# zones that stay local on every server (compared lowercase, without trailing dot)
EXCLUDE = {
    "localhost",
    "0.0.127.in-addr.arpa",
    "127.in-addr.arpa",
    "255.in-addr.arpa",
    "0.in-addr.arpa",
    ipaddress.ip_address("::1").reverse_pointer,  # exact 32-nibble name
}
EXCLUDE_FILE_PREFIXES = ()  # e.g. ("/usr/local/etc/namedb/local/",)

ZONE_PRIMARY_TYPES = {"primary", "master"}
ZONE_SECONDARY_TYPES = {"secondary", "slave"}


def _parse_zones_from_file(conf: str, zone_types: set[str]) -> tuple[str, list[tuple[str, str, int, str]]]:
    """Parse zones from a config file, filtering by the given zone types.
    
    Returns (directory_base, zones_list) where:
    - directory_base is the value of the directory directive (empty string if absent)
    - zones_list is [(zone_name, file_path, line_number, block_text)] for matching zones.
    file_path is the original path from the config (relative kept relative).
    line_number is the 1-based line in the config file where the zone block starts.
    block_text is the full original zone block text (from 'zone' to '};' inclusive).
    """
    conf = Path(conf)
    if not conf.exists():
        logger.error(f"Config file {conf} does not exist")
        return "", []
    try:
        txt = conf.read_text(encoding="utf-8")
    except OSError as e:
        logger.error(f"Cannot read config file {conf}: {e}")
        return "", []

    # Try to find a directory directive; if absent, use empty string (absolute paths only)
    d = re.search(r'^\s*directory\s+"([^"]+)"', txt, re.M)
    base = d.group(1) if d else ""

    zones = []
    for m in re.finditer(r'zone\s+"([^"]+)"(?:\s+\w+)?\s*\{', txt):
        name = m.group(1).rstrip(".").lower()
        if not name or name in EXCLUDE:
            logger.debug(f"Skipping zone {name}: excluded")
            continue
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(txt[i], 0)
            i += 1
        # Include trailing semicolon after closing brace
        end = i
        rest = txt[end:].lstrip()
        if rest.startswith(";"):
            end += len(txt[end:]) - len(rest) + 1
        body = txt[m.end():i]
        t = re.search(r'type\s+(\w+)', body)
        f = re.search(r'file\s+"([^"]+)"', body)
        if not (t and t.group(1).lower() in zone_types and f):
            logger.debug(f"Skipping zone {name}: type not in {zone_types}")
            continue
        path = f.group(1)
        if path.startswith(EXCLUDE_FILE_PREFIXES):
            logger.debug(f"Skipping zone {name}: file path starts with excluded prefix")
            continue
        line_no = txt[:m.start()].count("\n") + 1
        block_text = txt[m.start():end]
        zones.append((m.group(1), path, line_no, block_text))
    return (base, zones)


def parse_primary_zones_from_file(conf: str, zone_types: set[str] | None = None) -> tuple[str, list[tuple[str, str, int, str]]]:
    """Parse primary/master zones from a config file. Returns (directory_base, zones_list)."""
    return _parse_zones_from_file(conf, zone_types or ZONE_PRIMARY_TYPES)


def parse_secondary_zones_from_file(conf: str, zone_types: set[str] | None = None) -> tuple[str, list[tuple[str, str, int, str]]]:
    """Parse secondary/slave zones from a config file. Returns (directory_base, zones_list)."""
    return _parse_zones_from_file(conf, zone_types or ZONE_SECONDARY_TYPES)


def _transform_zone_block(block_text: str, file_path: str, source_types: set[str], target_type: str,
                          add_primaries: bool | None = None, primaries_content: str = "") -> str:
    """Transform a zone block from one type to another.
    
    Preserves the original multi-line format, indentation, and comments.
    
    Parameters:
        block_text: The original zone block text.
        file_path: The zone file path (already substituted if needed).
        source_types: Set of source type names to match (e.g., {"primary", "master"}).
        target_type: The target type name (e.g., "secondary").
        add_primaries: If True, insert a primaries directive after the type line.
        primaries_content: Full content string for the primaries directive (e.g., "10.0.0.100;").
    """

    lines = block_text.split("\n")
    result_lines = []
    directive_added = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Handle the closing '};' — insert directive before it if not yet added
        if stripped == '};':
            indent = lines[0][:len(lines[0]) - len(lines[0].lstrip())] if lines[0].lstrip() else "    "
            if add_primaries and not directive_added and primaries_content:
                result_lines.append(f'{indent}type {target_type};')
                result_lines.append(f'{indent}primaries {{ {primaries_content} }};')
                directive_added = True
            result_lines.append('};')
            i += 1
            continue

        # Replace source type with target type
        type_match = re.match(r'^(\s*)type\s+(' + '|'.join(source_types) + r')\s*;', line)
        if type_match:
            indent = type_match.group(1)
            result_lines.append(f'{indent}type {target_type};')
            if add_primaries and primaries_content:
                result_lines.append(f'{indent}primaries {{ {primaries_content} }};')
            directive_added = True
            i += 1
            continue

        # Skip the primaries directive when removing it
        if not add_primaries and re.match(r'^\s*primaries\s+\{', stripped):
            i += 1
            continue

        # Update file path if present
        file_match = re.match(r'^(\s*file\s+")([^"]+)(".*)$', line)
        if file_match:
            result_lines.append(f'{file_match.group(1)}{file_path}{file_match.group(3)}')
            i += 1
            continue

        # Keep all other lines as-is (allow-query, comments, etc.)
        result_lines.append(line)
        i += 1

    return "\n".join(result_lines)


def _convert(args: argparse.Namespace, zone_types: set[str], target_type: str, add_primaries: bool, comment: str) -> None:
    """Shared logic for gen and restore: parse, transform, and write zone config.
    
    Parameters:
        args: Parsed CLI arguments.
        zone_types: Set of source zone types to filter (e.g., {"primary", "master"}).
        target_type: Target type name (e.g., "secondary").
        add_primaries: If True, insert primaries directive; if False, remove it.
        comment: Comment header line for the output file.
    """
    # Choose parser based on zone types
    if zone_types == ZONE_PRIMARY_TYPES:
        directory_base, zones = parse_primary_zones_from_file(args.conf)
    else:
        directory_base, zones = parse_secondary_zones_from_file(args.conf)

    # Read the original config to preserve blank lines between zone blocks
    conf = Path(args.conf)
    try:
        orig_lines = conf.read_text().splitlines(keepends=True)
    except OSError:
        orig_lines = []

    lines = [comment]
    if directory_base:
        lines.append(f'directory "{directory_base}";')
        lines.append("")

    prev_end_pos = None
    for name, file_path, line_no, block_text in zones:
        block_end_line = line_no + block_text.count("\n")

        if prev_end_pos is not None and orig_lines:
            blank_count = 0
            for i in range(prev_end_pos, block_end_line):
                if i < len(orig_lines) and orig_lines[i].strip() == "":
                    blank_count += 1
            for _ in range(blank_count):
                lines.append("")

        # Resolve relative file path against directory base for db_path substitution
        is_relative = directory_base and not file_path.startswith("/")
        resolve_path = str(PurePosixPath(directory_base) / file_path) if is_relative else file_path

        # Apply db_path substitution on the resolved path
        if args.db_path_find and args.db_path_replace:
            resolve_path = resolve_path.replace(args.db_path_find, args.db_path_replace)

        # If the substituted path still starts with the directory base, keep it relative
        output_path = resolve_path
        if is_relative:
            try:
                output_path = str(PurePosixPath(resolve_path).relative_to(directory_base))
            except ValueError:
                pass

        transformed = _transform_zone_block(block_text, output_path, zone_types, target_type,
                                            add_primaries=add_primaries,
                                            primaries_content=args.primaries)
        lines.append(transformed)
        prev_end_pos = block_end_line

    tmp = Path(args.out + ".new")
    try:
        tmp.write_text("\n".join(lines) + "\n")
        tmp.replace(args.out)
        logger.info(f"{len(zones)} zones written to {args.out}")
    except OSError as e:
        logger.error(f"Cannot write output file {args.out}: {e}")


def gen(args: argparse.Namespace) -> None:
    """Generate a secondary-zone config from a primary-zone config."""
    _convert(args, ZONE_PRIMARY_TYPES, "secondary", add_primaries=True,
             comment="// generated by bind-zone-sync, do not edit")


def restore(args: argparse.Namespace) -> None:
    """Convert a secondary-zone config back to a primary-zone config."""
    _convert(args, ZONE_SECONDARY_TYPES, "primary", add_primaries=False,
             comment="// generated by bind-zone-sync restore, do not edit")


def main() -> None:
    args = parse_args()

    # Configure logging with user-friendly format
    level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    cmds = {"gen": gen, "restore": restore}
    cmds[args.command](args)


if __name__ == "__main__":
    main()
