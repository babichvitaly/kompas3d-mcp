"""Synthetic Git integration; no network, existing repository or CAD access."""

import importlib.util
import shutil
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'zip_benchmark', Path(__file__).resolve().parents[1] / 'scripts/benchmark_zip_packs.py')
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


@pytest.mark.parametrize('scenario', ['same-tail-shrinking', 'renamed', 'unrelated', 'stable-path'])
def test_pack_receiver_reconstruction_preservation_and_bitmap_conditions(tmp_path, scenario):
    git = shutil.which('git')
    if git is None:
        pytest.skip('Git executable required for synthetic integration')
    result = bench.benchmark(tmp_path / 'new-fixture', git, entries=8,
                             chunk_bytes=65536, scenario=scenario)
    assert result['source_unchanged'] and not result['network_used']
    assert all(row['receiver_verified'] for row in result['rows'])
    rows = {row['variant']: row for row in result['rows']}
    # Heuristic byte sizes are not a Git compatibility contract. Assert observed
    # compression behavior on the versions measured by this checkpoint only.
    if result['git_version'].split()[2].startswith(('2.54.', '2.56.')):
        baseline = rows['baseline']['ordinary_thin_bytes']
        if scenario == 'same-tail-shrinking':
            assert rows['pair']['ordinary_thin_bytes'] == baseline
            assert rows['full-no-bitmap']['ordinary_thin_bytes'] == baseline
            assert rows['full-bitmap']['ordinary_thin_bytes'] < baseline / 3
            assert rows['full-bitmap']['no_bitmap_thin_bytes'] == baseline
        elif scenario == 'stable-path':
            assert rows['full-bitmap']['ordinary_thin_bytes'] > baseline * 3
            assert rows['full-bitmap']['no_bitmap_thin_bytes'] == baseline
        else:
            # A full bitmap alone cannot create a useful new->old delta when
            # ordering favors the reverse delta or payloads have no similarity.
            assert rows['full-bitmap']['ordinary_thin_bytes'] > baseline * .9


def test_benchmark_rejects_existing_destination_before_any_git_call(tmp_path, monkeypatch):
    evidence = tmp_path / 'existing'
    evidence.mkdir()
    marker = evidence / 'preserve'
    marker.write_text('user data')
    monkeypatch.setattr(bench, 'git_run', lambda *a, **kw: pytest.fail('must not call Git'))
    with pytest.raises(FileExistsError):
        bench.benchmark(evidence, 'unused')
    assert marker.read_text() == 'user data'
