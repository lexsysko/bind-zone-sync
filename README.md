
# bind-zone-sync

Manage BIND zone configuration files: generate secondary-zone configs from primary-zone configs, and convert secondary configs back to primary configs.

## Features

- **`gen`** — Read a primary zone config and produce a secondary zone config, preserving the original multi-line formatting, blank lines, indentation, and comments.
- **`restore`** — Convert a secondary zone config back to a primary zone config, removing the `primaries` directive and restoring `type primary`.
- **`directory` directive preservation** — If the input config uses a `directory` directive with relative file paths, the output preserves the directive and keeps paths relative.
- **DB path substitution** — Automatically rewrite zone file paths (e.g., `primary/` → `secondary/`) during conversion.
- **Custom primaries content** — The `--primaries` option accepts any string for the `primaries` directive, supporting multiple IPs, TSIG keys, or global settings.

## Installation

```bash
pip install bind-zone-sync
# or
uv run bind-zone-sync --help
```

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

This changes file paths like `/usr/local/etc/namedb/primary/app1.example.net.db` to `/usr/local/etc/namedb/secondary/app1.example.net.db`.

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

## Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--conf` | `/usr/local/etc/namedb/zones-primary.conf.auto` | Input zone config file |
| `--out` | `/usr/local/etc/namedb/zones-secondary.conf.auto` | Output zone config file |
| `--primaries` | `10.0.0.100;` | Full content for the `primaries` directive (e.g., `"10.0.0.100;"`, `"10.0.0.100; 10.0.0.101;"`, `'10.0.0.100; key "mykey";'`) |
| `--db-path-find` | `/usr/local/etc/namedb/primary/` | Path prefix in zone file paths to replace |
| `--db-path-replace` | `""` | Replacement path prefix; empty = keep original paths |
| `--log-level` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

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

The `directory` directive is preserved, and the relative file path `"app1.example.net.db"` stays relative instead of being expanded to an absolute path.

### Example

**Primary input:**

```
zone "app1.example.net" {
    type primary;
    allow-query { any; };
    file "/usr/local/etc/namedb/primary/app1.example.net.db";
};
```

**Secondary output (`gen`):**

```
zone "app1.example.net" {
    type secondary;
    primaries { 10.0.0.100; };
    allow-query { any; };
    file "/usr/local/etc/namedb/secondary/app1.example.net.db";
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
