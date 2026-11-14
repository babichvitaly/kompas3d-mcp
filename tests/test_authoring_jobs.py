import hashlib
import json

import pytest

from kompas_mcp import authoring_jobs
from kompas_mcp.authoring_jobs import SavedJobJournal, author_jobs_checkpointed, recover_saved_jobs


def saved(tmp_path, name):
    path = tmp_path / (name + '.synthetic')
    path.write_text('synthetic saved artifact ' + name)
    return {'job_id': name, 'path': str(path), 'sha256_at_save': hashlib.sha256(path.read_bytes()).hexdigest()}


def test_third_job_failure_retains_two_saved_jobs_on_disk_without_reauthoring(tmp_path):
    journal = SavedJobJournal(tmp_path / 'journal')
    calls = []
    def author(name, publish):
        calls.append(name)
        if name == 'third':
            raise RuntimeError('Synthetic third-sheet failure')
        publish(saved(tmp_path, name))
        assert (journal.directory / 'checkpoint.json').is_file()  # before next author call
    result = author_jobs_checkpointed(['first', 'second', 'third'], author, journal)
    assert result['status'] == 'failed' and result['checkpointed_jobs'] == ['first', 'second']
    assert calls == ['first', 'second', 'third']
    assert [j['job_id'] for j in recover_saved_jobs(journal.directory)['saved_jobs']] == ['first', 'second']
    assert json.loads((journal.directory / 'checkpoint.json').read_text())['saved_jobs'][1]['job_id'] == 'second'


def test_post_save_exception_still_retains_the_already_checkpointed_current_job(tmp_path):
    journal = SavedJobJournal(tmp_path / 'journal')
    def author(name, publish):
        publish(saved(tmp_path, name))
        raise RuntimeError('After Save/checkpoint, before normal return')
    result = author_jobs_checkpointed(['one', 'two'], author, journal)
    assert result['checkpointed_jobs'] == ['one'] and result['failed_job'] == 'one'


def test_missing_checkpoint_blocks_next_job(tmp_path):
    calls = []
    result = author_jobs_checkpointed(['one', 'two'], lambda name, publish: calls.append(name),
                                      SavedJobJournal(tmp_path / 'journal'))
    assert result['status'] == 'failed' and calls == ['one']


def test_index_failure_has_individual_recovery_receipt_and_cannot_be_swallowed(tmp_path, monkeypatch):
    journal = SavedJobJournal(tmp_path / 'journal')
    monkeypatch.setattr(authoring_jobs, '_atomic_json', lambda *a: (_ for _ in ()).throw(OSError('disk failure')))
    calls = []
    def author(name, publish):
        calls.append(name)
        try:
            publish(saved(tmp_path, name))
        except OSError:
            pass  # caller swallowing a checkpoint error still cannot authorize next job
    result = author_jobs_checkpointed(['one', 'two'], author, journal)
    assert result['status'] == 'failed' and calls == ['one']
    assert recover_saved_jobs(journal.directory)['saved_jobs'][0]['job_id'] == 'one'


def test_later_owned_writeback_does_not_make_a_saved_job_never_authored(tmp_path):
    journal = SavedJobJournal(tmp_path / 'journal')
    job = saved(tmp_path, 'one')
    journal.publish(job)
    (tmp_path / 'one.synthetic').write_text('later authorized owned writeback')
    recovered = recover_saved_jobs(journal.directory)['saved_jobs']
    assert recovered[0]['job_id'] == 'one' and recovered[0]['artifact_state'] == 'changed'
    assert not recovered[0]['retry_allowed']


def test_no_adoption_of_existing_journal(tmp_path):
    directory = tmp_path / 'journal'
    directory.mkdir()
    with pytest.raises(FileExistsError):
        SavedJobJournal(directory)


def test_torn_last_receipt_does_not_erase_recoverable_saved_prefix(tmp_path):
    journal = SavedJobJournal(tmp_path / 'journal')
    journal.publish(saved(tmp_path, 'one'))
    (journal.directory / 'saved-000002.json').write_text('{torn')
    recovered = recover_saved_jobs(journal.directory)
    assert [j['job_id'] for j in recovered['saved_jobs']] == ['one']
    assert len(recovered['invalid_receipts']) == 1 and not recovered['retry_allowed']


def test_escaped_publisher_cannot_republish_after_its_job_has_returned(tmp_path):
    journal = SavedJobJournal(tmp_path / 'journal')
    escaped = []
    def author(name, publish):
        if escaped:
            with pytest.raises(ValueError, match='active checkpoint'):
                escaped[0](escaped[1])
        payload = saved(tmp_path, name)
        publish(payload)
        if not escaped:
            escaped.extend([publish, payload])
    result = author_jobs_checkpointed(['one', 'two'], author, journal)
    assert result['status'] == 'all_jobs_checkpointed'
    assert result['checkpointed_jobs'] == ['one', 'two']
