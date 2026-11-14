"""Durable saved-job publication before the next authoring job starts."""

import hashlib
import json
import os
from pathlib import Path

from pydantic import TypeAdapter

from .job_results import _atomic_json
from .state_oracles import Evidence, Key
from .view_state import Sha256


class SavedJob(Evidence):
    job_id: Key
    path: Key
    sha256_at_save: Sha256  # checkpoint, not a final publication seal


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class SavedJobJournal:
    def __init__(self, directory):
        self.directory = Path(directory)
        if not self.directory.is_absolute() or not self.directory.parent.is_dir():
            raise ValueError('Use a new absolute journal directory with an existing parent')
        self.directory.mkdir()  # exclusive: never adopt/retry into an existing journal
        self.saved = []

    def publish(self, payload):
        job = SavedJob.model_validate(payload)
        path = Path(job.path)
        if not path.is_absolute() or not path.is_file():
            raise ValueError('Saved job must name an existing absolute artifact')
        if _sha(path) != job.sha256_at_save:
            raise ValueError('Artifact differs from the declared save checkpoint')
        if any(j.job_id == job.job_id or j.path == job.path for j in self.saved):
            raise ValueError('Duplicate job/path checkpoint')
        # Persist individual receipts first; recovery works even if index publication fails.
        entry = self.directory / f'saved-{len(self.saved)+1:06}.json'
        with entry.open('x', encoding='utf-8') as stream:
            json.dump(job.model_dump(), stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != 'nt':
            fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        self.saved.append(job)
        _atomic_json(self.directory / 'checkpoint.json', {'saved_jobs': [j.model_dump() for j in self.saved]})


def recover_saved_jobs(directory):
    """Read durable job receipts; changed bytes do not mean 'never authored'."""
    recovered, invalid = [], []
    for entry in sorted(Path(directory).glob('saved-*.json')):
        try:
            job = SavedJob.model_validate_json(entry.read_text())
        except (OSError, ValueError) as exc:
            invalid.append({'receipt': str(entry), 'error': str(exc)})
            continue
        artifact = Path(job.path)
        state = 'missing'
        try:
            if artifact.is_file():
                state = 'unchanged' if _sha(artifact) == job.sha256_at_save else 'changed'
        except OSError:
            state = 'unreadable'
        recovered.append({**job.model_dump(), 'artifact_state': state, 'retry_allowed': False})
    return {'saved_jobs': recovered, 'invalid_receipts': invalid, 'retry_allowed': False}


def author_jobs_checkpointed(names, author_one, journal):
    """author_one(name, publish_saved) must publish immediately after each Save.

    A post-save exception retains that job. A missing checkpoint blocks the next
    job. No automatic resume, reauthoring, rollback or native operation occurs here.
    """
    result = {'status': 'failed', 'reported_saved_jobs': [], 'checkpointed_jobs': [],
              'retry_allowed': False, 'native_acceptance': 'pending'}
    current = None
    try:
        names = TypeAdapter(list[Key]).validate_python(names)
        if not names or len(names) != len(set(names)):
            raise ValueError('Explicit unique authoring jobs required')
        def make_publisher(job_name):
            state = {'published': False, 'checkpointed': False, 'active': True}
            def publish_saved(payload):
                job = SavedJob.model_validate(payload)
                if not state['active'] or state['published'] or job.job_id != job_name:
                    raise ValueError('One exact active checkpoint per current job required')
                state['published'] = True  # record an uncertain publication, never replay Save
                result['reported_saved_jobs'].append(job.model_dump())
                journal.publish(job)
                result['checkpointed_jobs'].append(job.job_id)
                state['checkpointed'] = True
            return publish_saved, state
        for current in names:
            publish, state = make_publisher(current)
            try:
                author_one(current, publish)
            finally:
                state['active'] = False
            if not state['checkpointed']:
                raise ValueError('Author returned without durably checkpointing its saved job')
        result['status'] = 'all_jobs_checkpointed'
    except Exception as exc:  # noqa: BLE001 - partial saved jobs are the deliverable on failure
        result.update(failed_job=current, error=f'{type(exc).__name__}: {exc}',
                      recovery='Read saved receipts and reconcile the current job; never reauthor automatically')
    return result
