import pytest
import core


@pytest.mark.parametrize('history,evidence', [
    ([{'session_id': 'actual', 'exit_code': False}], None),
    ([{'session_id': 'actual', 'exit_code': 0.0}], None),
    (None, None), (0, None), ([], {}),
])
def test_malformed_historical_seed_evidence_cannot_grant(history, evidence, tmp_path):
    target = core.ValidatedProfile('worker', 'worker', str(tmp_path))
    request = {'profile_home': target.home, 'requested_session_id': 'actual'}
    status = {'status': 'cancelled', 'child_session_id': 'actual',
              'recovery_history': history, 'session_identity_evidence': evidence}
    assert core._resume_record_matches(request, status, target, 'actual') is False


def test_valid_observed_history_admits_same_identity(tmp_path):
    target = core.ValidatedProfile('worker', 'worker', str(tmp_path))
    request = {'profile_home': target.home, 'requested_session_id': 'actual'}
    status = {'status': 'cancelled', 'child_session_id': 'actual',
              'recovery_history': [{'session_id': 'actual', 'exit_code': 0}]}
    assert core._resume_record_matches(request, status, target, 'actual') is True
