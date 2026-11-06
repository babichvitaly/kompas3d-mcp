"""Synthetic-only local Git/ZIP pack benchmark. Never accepts an existing repo.

Creates a new output directory; preserves evidence and never pushes, repacks,
prunes, resets or edits user configuration. Run explicitly, outside CAD flows.
"""

import argparse
import hashlib
import json
import os
import random
import subprocess
import time
import zipfile
from pathlib import Path


def clean_env():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('GIT_') and k not in {'SSH_ASKPASS'}}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0',
               GIT_AUTHOR_NAME='Synthetic Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_NAME='Synthetic Fixture',
               GIT_COMMITTER_EMAIL='fixture@example.invalid',
               GIT_AUTHOR_DATE='2020-01-01T00:00:00Z',
               GIT_COMMITTER_DATE='2020-01-01T00:00:00Z')
    return env


def git_run(git, repo, args, data=None, extra=None):
    env = clean_env()
    env.update(extra or {})
    return subprocess.run([git, '-C', str(repo), *args], input=data, env=env,
                          capture_output=True, check=True, timeout=60).stdout


def tree_hash(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def write_zip(path, root, payloads):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for i, payload in enumerate(payloads):
            info = zipfile.ZipInfo(f'{root}/payload-{i:03}.bin', (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, payload)


def benchmark(output, git, *, entries=24, chunk_bytes=262144, scenario='renamed'):
    output = Path(output)
    output.mkdir()  # must be new, including on failure; never retry into this directory
    repo = output / 'source'
    repo.mkdir()
    git_run(git, repo, ['init', '-q', '--initial-branch=main', '--object-format=sha1',
                        '--template='])
    rng = random.Random(1057)
    payloads = [rng.randbytes(chunk_bytes) for _ in range(entries)]
    old_path = repo / ('version-one-common-payload-package.zip'
                       if scenario == 'same-tail-shrinking' else 'release-one.zip')
    old_payloads = payloads + [rng.randbytes(chunk_bytes)] if scenario in {'shrinking', 'same-tail-shrinking'} else payloads
    write_zip(old_path, 'release-one', old_payloads)
    git_run(git, repo, ['add', '--', old_path.name])
    git_run(git, repo, ['-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture base'])
    old = git_run(git, repo, ['rev-parse', 'HEAD']).strip().decode()
    old_blob = git_run(git, repo, ['rev-parse', f'{old}:{old_path.name}']).strip().decode()
    if scenario == 'unrelated':
        payloads = [rng.randbytes(chunk_bytes) for _ in range(entries)]
    else:
        payloads[-1] = rng.randbytes(chunk_bytes)
    new_path = old_path if scenario == 'stable-path' else repo / 'release-two-different.zip'
    if scenario == 'same-tail-shrinking':
        new_path = repo / 'version-two-common-payload-package.zip'
    write_zip(new_path, 'release-two-different', payloads)
    git_run(git, repo, ['add', '--', new_path.name])
    git_run(git, repo, ['-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture update'])
    new = git_run(git, repo, ['rev-parse', 'HEAD']).strip().decode()
    new_blob = git_run(git, repo, ['rev-parse', f'{new}:{new_path.name}']).strip().decode()
    revisions = f'{new}\n^{old}\n'.encode()
    baseline_snapshot = tree_hash(repo)
    thin_args = ['pack-objects', '--revs', '--stdout', '--thin', '--delta-base-offset']
    rows = []
    for variant in ('baseline', 'pair', 'full-no-bitmap', 'full-bitmap',
                    'seeded-full-no-bitmap', 'seeded-full-bitmap'):
        env, preparation = {}, 0.
        cache = output / variant
        cache.mkdir()
        if variant != 'baseline':
            objects = cache / 'objects'
            (objects / 'pack').mkdir(parents=True)
            env = {'GIT_OBJECT_DIRECTORY': str(objects.resolve()),
                   'GIT_ALTERNATE_OBJECT_DIRECTORIES': str((repo / '.git/objects').resolve())}
            start = time.monotonic()
            if variant.startswith('seeded'):
                git_run(git, repo, ['pack-objects', str((objects / 'pack/seed').resolve())],
                        f'{old_blob}\n{new_blob}\n'.encode(), env)
            args = ['pack-objects']
            data = f'{old_blob}\n{new_blob}\n'.encode()
            if variant.startswith(('full', 'seeded')):
                args += ['--all', '--revs']
                data = b''
            if variant.endswith('bitmap') and not variant.endswith('no-bitmap'):
                args += ['--write-bitmap-index']
            args += [str((objects / 'pack/pack').resolve())]
            git_run(git, repo, args, data, env)
            preparation = time.monotonic() - start
            for pack in (objects / 'pack').glob('*.pack'):
                git_run(git, repo, ['index-pack', '--verify', str(pack.resolve())], extra=env)
                detail = git_run(git, repo, ['verify-pack', '-v', str(pack.with_suffix('.idx').resolve())],
                                 extra=env)
                (cache / 'verify-pack.txt').write_bytes(detail)
            if variant.endswith('bitmap') and not variant.endswith('no-bitmap'):
                assert list((objects / 'pack').glob('*.bitmap'))
                git_run(git, repo, ['rev-list', '--test-bitmap', new], extra=env)
        start = time.monotonic()
        thin = git_run(git, repo, thin_args, revisions, env)
        elapsed = time.monotonic() - start
        (cache / 'ordinary-thin.pack').write_bytes(thin)
        # Receiver has only base history, never the new commit/blob as an alternate.
        receiver = cache / 'receiver'
        receiver.mkdir()
        git_run(git, receiver, ['init', '--bare', '-q', '--object-format=sha1', '--template='])
        base_pack = git_run(git, repo, ['pack-objects', '--revs', '--stdout'], f'{old}\n'.encode())
        git_run(git, receiver, ['index-pack', '--stdin'], base_pack)
        git_run(git, receiver, ['index-pack', '--stdin', '--fix-thin'], thin)
        recovered = git_run(git, receiver, ['cat-file', 'blob', f'{new}:{new_path.name}'])
        assert recovered == new_path.read_bytes(), 'receiver did not reconstruct exact new ZIP'
        bitmap_disabled = None
        if variant.endswith('bitmap') and not variant.endswith('no-bitmap'):
            bitmap_disabled = len(git_run(git, repo, thin_args + ['--no-use-bitmap-index'],
                                         revisions, env))
        rows.append({'variant': variant, 'ordinary_thin_bytes': len(thin),
                     'prepare_seconds': round(preparation, 4), 'thin_seconds': round(elapsed, 4),
                     'new_blob_delta_base': next((line.split()[6] for line in
                         (cache / 'verify-pack.txt').read_text().splitlines()
                         if line.startswith(new_blob + ' ') and len(line.split()) == 7), None)
                         if variant != 'baseline' else None,
                     'cache_bytes': sum(p.stat().st_size for p in cache.glob('objects/pack/*')),
                     'no_bitmap_thin_bytes': bitmap_disabled, 'receiver_verified': True})
    assert tree_hash(repo) == baseline_snapshot, 'source repository changed during measurement'
    result = {'schema': 'synthetic-zip-pack-benchmark/1', 'scenario': scenario,
              'git_version': git_run(git, repo, ['--version']).decode().strip(),
              'entries': entries, 'chunk_bytes': chunk_bytes,
              'pack_command': ['pack-objects', '--revs', '--stdout', '--thin', '--delta-base-offset'], 'new_zip_bytes': new_path.stat().st_size,
              'source_unchanged': True, 'network_used': False, 'rows': rows}
    (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New absolute evidence directory')
    parser.add_argument('--git', required=True, help='Absolute Git executable')
    parser.add_argument('--scenario', choices=['renamed', 'stable-path', 'unrelated', 'shrinking', 'same-tail-shrinking'], default='renamed')
    args = parser.parse_args()
    if not args.output.is_absolute() or not Path(args.git).is_absolute():
        parser.error('Use absolute output and git paths')
    print(json.dumps(benchmark(args.output, args.git, scenario=args.scenario), indent=2))


if __name__ == '__main__':
    main()
