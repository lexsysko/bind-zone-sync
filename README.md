# bind-zone-sync

Manage BIND zone configuration files: generate secondary-zone configs from primary-zone configs, restore primary configs from
secondary configs, and build legacy named.conf files from zone db file folders.

## Features

- **`gen`** — Read a primary zone config and produce a secondary zone config, preserving the original multi-line formatting, blank
  lines, indentation, and comments.
- **`restore`** — Convert a secondary zone config back to a primary zone config, removing the `primaries` directive and restoring
  `type primary`.
- **`convert`** — Scan a folder of BIND zone db files, extract zone names from SOA records, and generate a legacy `named.conf`
  with secondary zone blocks — useful for syncing zones when using BIND's `catalog.zone` feature.
- **`catalog`** — Parse a `named.conf` file, extract all zone domains, and produce a `catalog.zone` zone list where each
  zone key is the SHA1 hash of its domain name — ready to include in BIND's `catalog` directive.
- **`directory` directive preservation** — If the input config uses a `directory` directive with relative file paths, the output
  preserves the directive and keeps paths relative.
- **DB path substitution** — Automatically rewrite zone file paths (e.g., `primary/` → `secondary/`) during conversion.
- **Custom primaries content** — The `--primaries` option accepts any string for the `primaries` directive, supporting multiple
  IPs, TSIG keys, or global settings.
- **Custom comment header** — The `--comment` option lets you set a custom comment line at the top of the output file.

## Installation

```bash
pip install bind-zone-sync
# or
uv run bind-zone-sync --help
# or
uvx bind-zone-sync --help
```

### Standalone Usage (No Installation Required)

The `bind_zone_sync.py` script is self-contained and uses only Python standard library modules. You can copy it to any location
and run it directly without installing the package:

```bash 
# Download or copy the script
curl -o bind_zone_sync.py https://raw.githubusercontent.com/lexsysko/bind-zone-sync/main/src/bind_zone_sync/bind_zone_sync.py

# Run directly with Python
python bind_zone_sync.py gen --conf zones-primary.conf --out zones-secondary.conf
python bind_zone_sync.py restore --conf zones-secondary.conf --out zones-primary.conf
python bind_zone_sync.py convert --conf /path/to/zone-folder --out named.conf.legacy
python bind_zone_sync.py catalog --conf named.conf --out catalog.zone
```

This is useful when you don't have pip/uv available or want a quick one-off conversion without setting up a Python environment.

## Usage

### Generate Secondary Config (`gen`)

Convert a primary zone config to a secondary zone config:

```bash
bind-zone-sync gen --conf zones-primary.conf --out zones-secondary.conf
```

Each zone block is transformed:

- `type primary` → `type secondary`
- `primaries { <address>; };` directive is added after the type line
- All other directives (allow-query, file, etc.) are preserved as-is
- Blank lines between zones match the original file

**With DB path substitution:**

```bash
bind-zone-sync gen --conf zones-primary.conf --out zones-secondary.conf \
  --db-path-find /usr/local/etc/namedb/primary/ \
  --db-path-replace /usr/local/etc/namedb/secondary/
```

This changes file paths like `/usr/local/etc/namedb/primary/app1.example.net.db` to
`/usr/local/etc/namedb/secondary/app1.example.net.db`.

**With custom primaries content:**

```bash
# Single IP:
bind-zone-sync gen --conf zones-primary.conf --out zones-secondary.conf \
  --primaries "10.0.0.100;"

# Multiple IPs:
bind-zone-sync gen --conf zones-primary.conf --out zones-secondary.conf \
  --primaries "10.0.0.100; 10.0.0.101;"

# With TSIG key:
bind-zone-sync gen --conf zones-primary.conf --out zones-secondary.conf \
  --primaries '10.0.0.100; key "mykey";'
```

### Restore Primary Config (`restore`)

Convert a secondary zone config back to a primary zone config:

```bash
bind-zone-sync restore --conf zones-secondary.conf --out zones-primary.conf
```

Each zone block is transformed:

- `type secondary` → `type primary`
- `primaries { ... };` directive is removed
- All other directives are preserved as-is
- Blank lines between zones match the original file

**With DB path restoration:**

```bash
bind-zone-sync restore --conf zones-secondary.conf --out zones-primary.conf \
  --db-path-find /usr/local/etc/namedb/secondary/ \
  --db-path-replace /usr/local/etc/namedb/primary/
```

### Build Legacy Config from Zone DB Files (`convert`)

Scan a directory containing BIND zone db files and generate a legacy `named.conf`. The zone type depends on whether
`--primaries` is provided:

- **Without `--primaries`** — generates `type primary` zone blocks (for the primary/authoritative server).
- **With `--primaries`** — generates `type secondary` zone blocks with the `primaries` directive (for secondary servers,
  useful when using BIND's `catalog.zone` feature).

**Generate primary zones (default):**

```bash
bind-zone-sync convert --conf /path/to/zone-folder --out /usr/local/etc/namedb/named.conf.zones
```

Output:

```
zone "app1.example.net" {
    type primary;
    file "/path/to/zone-folder/db.app1.example.net";
};
```

**Generate secondary zones (with `--primaries`):**

```bash
bind-zone-sync convert --conf /path/to/zone-folder --out /usr/local/etc/namedb/named.conf.legacy-zones \
  --primaries "10.0.0.100;"
```

Output:

```
zone "app1.example.net" {
    type secondary;
    file "/path/to/zone-folder/db.app1.example.net";
    primaries { 10.0.0.100; };
};
```

**With custom comment header:**

```bash
bind-zone-sync convert --conf /path/to/zone-folder --out named.conf.legacy \
  --comment "// legacy zones for secondary sync"
```

The `convert` command:

- Scans the directory non-recursively, skipping hidden files (starting with `.`)
- Extracts zone names from `$ORIGIN` directives or SOA owner names
- Excludes well-known local zones (localhost, loopback, etc.)
- Writes `type primary` by default, or `type secondary` with `primaries` when `--primaries` is set

### Build Catalog Zone List (`catalog`)

Parse a `named.conf` file, extract all zone domains, and produce a `catalog.zone` zone list where each zone key is the
SHA1 hash of its domain name. This output is ready to include in BIND's `catalog` directive for automatic zone
synchronization between servers.

```bash
bind-zone-sync catalog --conf /usr/local/etc/namedb/named.conf --out /usr/local/etc/namedb/catalog.zone
```

Output:

```
// generated by bind-zone-sync, do not edit
a1b2c3d4e5f6789012345678901234567890abcd  app1.example.net;
b2c3d4e5f6789012345678901234567890abcde  app2.example.net;
```

Each line contains a SHA1 hash (the zone key) followed by the domain name. BIND uses these keys in its `catalog.zone`
feature to track and synchronize zones across servers.

The `catalog` command:

- Parses both `type primary` and `type secondary` zone blocks from the input config
- Excludes well-known local zones (localhost, loopback, etc.)
- Deduplicates zones by domain name
- Sorts output alphabetically by domain name
- Computes SHA1 hash of each domain name as the zone key

## Command-Line Options

| Option              | Default                                           | Description                                                                                                                       |
|---------------------|---------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `--conf`            | `/usr/local/etc/namedb/zones-primary.conf.auto`   | Input zone config file (for `gen`/`restore`/`catalog`) or zone db files directory (for `convert`)                                 |
| `--out`             | `/usr/local/etc/namedb/zones-secondary.conf.auto` | Output zone config file                                                                                                           |
| `--primaries`       | `""` (empty)                                      | When set, generates secondary zones with the `primaries` directive; when omitted, generates primary zones (e.g., `"10.0.0.100;"`) |
| `--db-path-find`    | `/usr/local/etc/namedb/primary/`                  | Path prefix in zone file paths to replace                                                                                         |
| `--db-path-replace` | `""`                                              | Replacement path prefix; empty = keep original paths                                                                              |
| `--comment`         | `// generated by bind-zone-sync, do not edit`     | Comment header line in the output file                                                                                            |
| `--log-level`       | `INFO`                                            | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`                                                                    |

## Excluded Zones

The following zones are automatically excluded from replication (they stay local on every server):

- `localhost`
- `0.0.127.in-addr.arpa`
- `127.in-addr.arpa`
- `255.in-addr.arpa`
- `0.in-addr.arpa`
- IPv6 loopback reverse zone

## Output Format

Both `gen` and `restore` preserve the original config file's formatting:

- **Multi-line zone blocks** — Each zone keeps its original indentation and line structure
- **Blank lines** — Blank lines between zone blocks are preserved from the original file
- **Comments** — Inline comments within zone blocks are kept
- **Directives** — All directives other than `type` and `primaries` are unchanged
- **`directory` directive** — If present in the input, it is copied to the output and file paths remain relative

### Directory Directive Example

**Primary input (with `directory`):**

```
directory "/usr/local/etc/namedb/zones";

zone "app1.example.net" {
    type primary;
    file "app1.example.net.db";
};
```

**Secondary output (`gen`):**

```
directory "/usr/local/etc/namedb/zones";

zone "app1.example.net" {
    type secondary;
    primaries { 10.0.0.100; };
    file "app1.example.net.db";
};
```

The `directory` directive is preserved, and the relative file path `"app1.example.net.db"` stays relative instead of being
expanded to an absolute path.

### Example

**Primary input:**

```
zone "app1.example.net" {
    type primary;
    allow-query { any; };
    file "/usr/local/etc/namedb/primary/db.app1.example.net";
};
```

**Secondary output (`gen`):**

```
zone "app1.example.net" {
    type secondary;
    primaries { 10.0.0.100; };
    allow-query { any; };
    file "/usr/local/etc/namedb/secondary/db.app1.example.net";
};
```

## Examples

### Test without BIND installed

```bash
# Generate secondary config from primary
uv run bind-zone-sync gen --conf zones-primary.conf --out zones-secondary.conf

# Restore primary config from secondary
uv run bind-zone-sync restore --conf zones-secondary.conf --out zones-primary.conf
```

### Full production workflow

```bash
# On the primary server: generate the secondary config
bind-zone-sync gen --conf /usr/local/etc/namedb/zones-primary.conf \
  --out /usr/local/etc/namedb/zones-secondary.conf \
  --primaries "10.0.0.100;" \
  --db-path-find /usr/local/etc/namedb/primary/ \
  --db-path-replace /usr/local/etc/namedb/secondary/

# Deploy zones-secondary.conf to the secondary server

# If you need to restore a primary config from a secondary backup
bind-zone-sync restore --conf /usr/local/etc/namedb/zones-secondary.conf \
  --out /usr/local/etc/namedb/zones-primary.conf \
  --db-path-find /usr/local/etc/namedb/secondary/ \
  --db-path-replace /usr/local/etc/namedb/primary/
```

### Legacy zones sync with catalog.zone

```bash
# On the primary server — build zone config with type primary
bind-zone-sync convert --conf /usr/local/etc/namedb/zones/ \
  --out /usr/local/etc/namedb/named.conf.zones

# On the secondary server — build zone config with type secondary
bind-zone-sync convert --conf /usr/local/etc/namedb/zones/ \
  --out /usr/local/etc/namedb/named.conf.legacy-zones \
  --primaries "10.0.0.100;"

# Build a catalog.zone zone list from named.conf (SHA1 keys)
bind-zone-sync catalog --conf /usr/local/etc/namedb/named.conf \
  --out /usr/local/etc/namedb/catalog.zone

# Include the generated config in your main named.conf
# include "/usr/local/etc/namedb/named.conf.zones";
# include "/usr/local/etc/namedb/named.conf.legacy-zones";
# catalog "catalog.zone" { zones "/usr/local/etc/namedb/catalog.zone"; };
```
