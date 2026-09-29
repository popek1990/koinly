"""The committed example must be exactly what the generator and the build produce."""
import filecmp
import tempfile
import unittest
from pathlib import Path

import make_example
from koinly_csv import build, config

EXAMPLE = make_example.EXAMPLE


def files_under(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


class ExampleTests(unittest.TestCase):
    def test_generator_reproduces_the_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            make_example.generate(Path(folder))
            generated = files_under(Path(folder))
            self.assertEqual(generated, [name for name in files_under(EXAMPLE)
                                         if not name.startswith(("expected", "output", "README"))])
            for name in generated:
                self.assertTrue(filecmp.cmp(Path(folder) / name, EXAMPLE / name, shallow=False), name)

    def test_build_reproduces_the_expected_output(self):
        with tempfile.TemporaryDirectory() as folder:
            result = build.build(config.load(EXAMPLE / "config.toml"), Path(folder))
            self.assertEqual([i for i in result.issues if i.level == "error"], [])
            self.assertEqual(files_under(Path(folder)), files_under(EXAMPLE / "expected"))
            for name in files_under(Path(folder)):
                self.assertTrue(filecmp.cmp(Path(folder) / name, EXAMPLE / "expected" / name, shallow=False), name)

    def test_example_warns_about_the_wallet_outside_koinly(self):
        with tempfile.TemporaryDirectory() as folder:
            result = build.build(config.load(EXAMPLE / "config.toml"), Path(folder))
        self.assertTrue(any("broken transfer" in issue.message for issue in result.issues))
        self.assertIn("Transfers Koinly should merge: 5", result.summary)


if __name__ == "__main__":
    unittest.main()
