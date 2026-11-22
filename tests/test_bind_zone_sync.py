import argparse
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from bind_zone_sync.bind_zone_sync import (
    parse_primary_zones_from_file,
    parse_secondary_zones_from_file,
    gen,
    restore,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _args(conf: str, out: str, **kwargs) -> argparse.Namespace:
    """Build a Namespace that mimics the CLI parser output."""
    defaults = dict(
        command="gen",
        conf=conf,
        out=out,
        primaries="10.0.0.100;",
        db_path_find="/usr/local/etc/namedb/primary/",
        db_path_replace="",
        log_level="INFO",
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestGenNoDirectory(unittest.TestCase):
    """gen without directory directive — absolute paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gen_converts_primary_to_secondary(self):
        """Basic gen: type primary → secondary, primaries added, paths unchanged."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "primary-no-dir.conf"), out)
        gen(args)

        text = Path(out).read_text()
        self.assertIn("type secondary;", text)
        self.assertIn("primaries { 10.0.0.100; };", text)
        self.assertIn("/usr/local/etc/namedb/primary/app1.example.net.db", text)
        self.assertNotIn("type primary;", text)

    def test_gen_preserves_blank_lines(self):
        """Blank lines between zone blocks are preserved."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "primary-no-dir.conf"), out)
        gen(args)

        lines = Path(out).read_text().splitlines()
        # There should be at least one blank line between the two zone blocks
        found_blank_between = False
        in_first = False
        for line in lines:
            if 'zone "app1.example.net"' in line:
                in_first = True
            elif in_first and line.strip() == "":
                found_blank_between = True
                break
            elif in_first and 'zone "app2.example.net"' in line:
                break
        self.assertTrue(found_blank_between, "Expected blank line between zone blocks")

    def test_gen_preserves_allow_query(self):
        """Non-type directives like allow-query are kept as-is."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "primary-no-dir.conf"), out)
        gen(args)

        self.assertIn("allow-query { any; };", Path(out).read_text())


class TestRestoreNoDirectory(unittest.TestCase):
    """restore without directory directive — absolute paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_converts_secondary_to_primary(self):
        """Basic restore: type secondary → primary, primaries removed."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "secondary-no-dir.conf"), out, command="restore")
        restore(args)

        text = Path(out).read_text()
        self.assertIn("type primary;", text)
        self.assertNotIn("primaries {", text)
        self.assertNotIn("type secondary;", text)

    def test_restore_preserves_file_path(self):
        """File paths are kept when no db-path-replace is set."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "secondary-no-dir.conf"), out, command="restore")
        restore(args)

        text = Path(out).read_text()
        self.assertIn("/usr/local/etc/namedb/secondary/app1.example.net.db", text)


class TestGenNoDirReplacePath(unittest.TestCase):
    """gen without directory — replace primary/ with secondary/ in file paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gen_replaces_db_path(self):
        """--db-path-replace changes primary/ to secondary/ in file paths."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(
            str(FIXTURES / "primary-no-dir.conf"),
            out,
            db_path_find="/usr/local/etc/namedb/primary/",
            db_path_replace="/usr/local/etc/namedb/secondary/",
        )
        gen(args)

        text = Path(out).read_text()
        self.assertIn("/usr/local/etc/namedb/secondary/app1.example.net.db", text)
        self.assertNotIn("/usr/local/etc/namedb/primary/", text)


class TestRestoreNoDirReplacePath(unittest.TestCase):
    """restore without directory — replace secondary/ with primary/ in file paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_replaces_db_path(self):
        """--db-path-replace changes secondary/ to primary/ in file paths."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(
            str(FIXTURES / "secondary-no-dir.conf"),
            out,
            command="restore",
            db_path_find="/usr/local/etc/namedb/secondary/",
            db_path_replace="/usr/local/etc/namedb/primary/",
        )
        restore(args)

        text = Path(out).read_text()
        self.assertIn("/usr/local/etc/namedb/primary/app1.example.net.db", text)
        self.assertNotIn("/usr/local/etc/namedb/secondary/", text)


class TestGenWithDirectory(unittest.TestCase):
    """gen with directory directive — relative paths preserved."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gen_preserves_directory(self):
        """Directory directive is preserved in output."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "primary-with-dir.conf"), out)
        gen(args)

        text = Path(out).read_text()
        self.assertIn('directory "/usr/local/etc/namedb/zones";', text)

    def test_gen_keeps_relative_paths(self):
        """File paths stay relative when directory is present."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "primary-with-dir.conf"), out)
        gen(args)

        text = Path(out).read_text()
        self.assertIn('file "app1.example.net.db";', text)
        self.assertNotIn("/usr/local/etc/namedb/zones/app1.example.net.db", text)

    def test_gen_converts_type(self):
        """Type is converted to secondary with primaries directive."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "primary-with-dir.conf"), out)
        gen(args)

        text = Path(out).read_text()
        self.assertIn("type secondary;", text)
        self.assertIn("primaries { 10.0.0.100; };", text)
        self.assertNotIn("type primary;", text)


class TestRestoreWithDirectory(unittest.TestCase):
    """restore with directory directive — relative paths preserved."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_preserves_directory(self):
        """Directory directive is preserved in output."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "secondary-with-dir.conf"), out, command="restore")
        restore(args)

        text = Path(out).read_text()
        self.assertIn('directory "/usr/local/etc/namedb/zones";', text)

    def test_restore_keeps_relative_paths(self):
        """File paths stay relative when directory is present."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "secondary-with-dir.conf"), out, command="restore")
        restore(args)

        text = Path(out).read_text()
        self.assertIn('file "app1.example.net.db";', text)

    def test_restore_converts_type(self):
        """Type is converted to primary and primaries directive is removed."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(str(FIXTURES / "secondary-with-dir.conf"), out, command="restore")
        restore(args)

        text = Path(out).read_text()
        self.assertIn("type primary;", text)
        self.assertNotIn("primaries {", text)
        self.assertNotIn("type secondary;", text)


class TestGenWithDirReplacePath(unittest.TestCase):
    """gen with directory — replace zones/ with secondary/ in file paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gen_replaces_db_path_with_directory(self):
        """When db-path-replace changes the path outside the directory base, paths become absolute."""
        out = os.path.join(self.tmp, "out.conf")
        args = _args(
            str(FIXTURES / "primary-with-dir.conf"),
            out,
            db_path_find="/usr/local/etc/namedb/zones/",
            db_path_replace="/usr/local/etc/namedb/secondary/",
        )
        gen(args)

        text = Path(out).read_text()
        # Path is replaced to secondary/ which is outside the directory base, so it becomes absolute
        self.assertIn("/usr/local/etc/namedb/secondary/app1.example.net.db", text)


class TestRestoreWithDirReplacePath(unittest.TestCase):
    """restore with directory — replace secondary/ with zones/ in file paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_replaces_db_path_with_directory(self):
        """Restore a secondary config with absolute paths back to primary with path substitution."""
        # First generate a secondary config with absolute paths under secondary/
        gen_out = os.path.join(self.tmp, "secondary.conf")
        args_gen = _args(
            str(FIXTURES / "primary-with-dir.conf"),
            gen_out,
            db_path_find="/usr/local/etc/namedb/zones/",
            db_path_replace="/usr/local/etc/namedb/secondary/",
        )
        gen(args_gen)

        # The generated secondary config has absolute paths and no directory directive
        # (since the replaced path is outside the directory base)
        gen_text = Path(gen_out).read_text()
        self.assertIn("/usr/local/etc/namedb/secondary/app1.example.net.db", gen_text)

        # Now restore it back — the secondary/ paths should be replaced with zones/
        restore_out = os.path.join(self.tmp, "restored.conf")
        args_restore = _args(
            gen_out,
            restore_out,
            command="restore",
            db_path_find="/usr/local/etc/namedb/secondary/",
            db_path_replace="/usr/local/etc/namedb/zones/",
        )
        restore(args_restore)

        text = Path(restore_out).read_text()
        self.assertIn("type primary;", text)
        self.assertNotIn("primaries {", text)
        # The generated secondary has no directory directive, so paths stay absolute
        self.assertIn("/usr/local/etc/namedb/zones/app1.example.net.db", text)


class TestParseZones(unittest.TestCase):
    """Test zone parsing functions directly."""

    def test_parse_primary_zones_no_dir(self):
        directory, zones = parse_primary_zones_from_file(str(FIXTURES / "primary-no-dir.conf"))
        self.assertEqual(directory, "")
        self.assertEqual(len(zones), 2)
        names = [z[0] for z in zones]
        self.assertIn("app1.example.net", names)
        self.assertIn("app2.example.net", names)

    def test_parse_primary_zones_with_dir(self):
        directory, zones = parse_primary_zones_from_file(str(FIXTURES / "primary-with-dir.conf"))
        self.assertEqual(directory, "/usr/local/etc/namedb/zones")
        self.assertEqual(len(zones), 2)

    def test_parse_secondary_zones_no_dir(self):
        directory, zones = parse_secondary_zones_from_file(str(FIXTURES / "secondary-no-dir.conf"))
        self.assertEqual(directory, "")
        self.assertEqual(len(zones), 2)

    def test_parse_secondary_zones_with_dir(self):
        directory, zones = parse_secondary_zones_from_file(str(FIXTURES / "secondary-with-dir.conf"))
        self.assertEqual(directory, "/usr/local/etc/namedb/zones")
        self.assertEqual(len(zones), 2)

    def test_excludes_localhost(self):
        """Localhost and loopback zones are excluded."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False)
        tmp.write(
            'zone "localhost" { type primary; file "/tmp/localhost.db"; };\n'
            'zone "app1.example.net" { type primary; file "/tmp/app1.db"; };\n'
        )
        tmp.close()
        try:
            _, zones = parse_primary_zones_from_file(tmp.name)
            names = [z[0] for z in zones]
            self.assertNotIn("localhost", names)
            self.assertIn("app1.example.net", names)
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
