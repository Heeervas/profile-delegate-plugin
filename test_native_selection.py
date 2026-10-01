import json
import pytest
import core
import native_approval


def test_target_selection_and_invalid_map_are_preallocation(tmp_path, monkeypatch):
    monkeypatch.delenv('PROFILE_DELEGATE_APPROVAL_REQUEST', raising=False)
    entry={'child_approval_mode':'deny','child_approval_modes_by_profile':{'worker':'profile'}}
    monkeypatch.setattr(core,'_plugin_entry',lambda:entry)
    from hermes_cli import profiles
    monkeypatch.setattr(profiles,'profile_exists',lambda name: name=='worker')
    policy=core.load_effective_policy()
    target=core.ValidatedProfile('worker','worker',str(tmp_path/'worker'))
    value=core.resolve_native_approval(policy,target)
    assert value['effective']=='profile'
    assert value['source']=='operator_target'
    before = list(tmp_path.iterdir())
    entry['child_approval_modes_by_profile']['worker']='bogus'
    with pytest.raises(core.ProfileDelegateError,match='invalid approval target'):
        core.load_effective_policy()
    assert list(tmp_path.iterdir()) == before


def test_frozen_resume_under_compatible_inherit_is_admitted(tmp_path, monkeypatch):
    target=core.ValidatedProfile('worker','worker',str(tmp_path/'worker'))
    ancestor=native_approval.snapshot('profile','yaml','caller','parent',{}, {'approvals':{'deny':['git push*']}})
    frozen=native_approval.snapshot('inherit','yaml','parent',target.home,{}, {}, ancestor=ancestor)
    a=tmp_path/'ancestor.json'
    a.write_text(json.dumps({'native_approval':ancestor}))
    monkeypatch.setenv('PROFILE_DELEGATE_APPROVAL_REQUEST',str(a))
    r=tmp_path/'runs'/'prior'
    r.mkdir(parents=True)
    (r/'request.json').write_text(json.dumps({'profile_home':target.home,'native_approval':frozen}))
    (r/'status.json').write_text(json.dumps({'child_session_id':'frozen'}))
    monkeypatch.setattr(core,'get_runs_root',lambda:r.parent)
    assert core.resume_native_approval(core.EffectivePolicy({},{}),target,'frozen')==frozen
