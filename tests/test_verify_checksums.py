"""CI runs `verify_checksums.py verify` on a fresh checkout, so a pass must
mean every output CSV matches the committed manifest, not that nothing was
compared."""
import json

import verify_checksums as vc


def _output(tmp_path, **csvs):
    out = tmp_path / "output"
    out.mkdir()
    for name, body in csvs.items():
        (out / f"{name}.csv").write_text(body)
    return out


def test_a_generated_manifest_verifies(tmp_path):
    out = _output(tmp_path, a="x\n1\n", b="y\n2\n")
    vc.generate_manifest(str(out))
    assert vc.verify_manifest(str(out))


def test_a_changed_file_fails(tmp_path):
    out = _output(tmp_path, a="x\n1\n")
    vc.generate_manifest(str(out))
    (out / "a.csv").write_text("x\n2\n")
    assert not vc.verify_manifest(str(out))


def test_an_empty_manifest_fails(tmp_path):
    out = _output(tmp_path, a="x\n1\n")
    (out / "checksums.json").write_text(json.dumps({"files": []}))
    assert not vc.verify_manifest(str(out))


def test_a_csv_missing_from_the_manifest_fails(tmp_path, capsys):
    out = _output(tmp_path, a="x\n1\n")
    vc.generate_manifest(str(out))
    (out / "new.csv").write_text("z\n3\n")
    assert not vc.verify_manifest(str(out))
    assert "NOT IN MANIFEST: new.csv" in capsys.readouterr().out
