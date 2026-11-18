from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.enums.enums import JobStatus
from api.exceptions import RetryNotAllowed
from api.services.ingestion import MAX_ATTEMPTS, _new_job


class FakeSession:
    def __init__(self, last_attempt):
        self.last_attempt = last_attempt
        self.jobs = []

    def scalar(self, statement):
        return self.last_attempt

    def add(self, job):
        self.jobs.append(job)

    def flush(self):
        self.jobs[-1].id = uuid4()


def test_new_job_starts_at_first_attempt_when_version_has_no_jobs():
    db = FakeSession(last_attempt=None)

    job = _new_job(db, SimpleNamespace(id=uuid4()))

    assert job.attempt == 1
    assert job.status == JobStatus.QUEUED
    assert job.celery_task_id == str(job.id)


def test_new_job_allows_final_configured_attempt():
    db = FakeSession(last_attempt=MAX_ATTEMPTS - 1)

    job = _new_job(db, SimpleNamespace(id=uuid4()))

    assert job.attempt == MAX_ATTEMPTS


def test_new_job_rejects_an_attempt_after_the_configured_limit():
    db = FakeSession(last_attempt=MAX_ATTEMPTS)

    with pytest.raises(RetryNotAllowed, match=f"failed {MAX_ATTEMPTS} times"):
        _new_job(db, SimpleNamespace(id=uuid4()))

    assert db.jobs == []
