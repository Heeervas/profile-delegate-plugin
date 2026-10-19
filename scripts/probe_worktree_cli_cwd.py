"""No-inference native CLI cwd probe. Usage: python probe_worktree_cli_cwd.py REQUEST RUN_DIR.

Runs parser/--in, real CLI config projection, terminal pwd/file read, native lazy
session creation and native resume restoration. No provider or DB patching.
"""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import core
    from hermes_cli._parser import build_top_level_parser
    from hermes_cli.main import _resolve_chat_session_args
    from hermes_state import SessionDB
    from run_agent import AIAgent
    from hermes_cli.cli_session_mixin import CLISessionMixin
    from tools.terminal_tool import terminal_tool

    request = json.loads(Path(sys.argv[1]).read_text())
    run_dir = Path(sys.argv[2])
    command = core.build_child_command(request, run_dir)
    native = command[command.index('--') + 1:]
    args = build_top_level_parser()[0].parse_args(native[3:])  # main consumes -p PROFILE before parsing
    _resolve_chat_session_args(args, False)
    # cli import projects the disposable profile's actual config to the environment.
    import cli  # noqa: F401 -- exercises native config import side effects
    core.execution.bind_cli_workspace(request)
    source = args.source
    os.environ['HERMES_SESSION_SOURCE'] = source
    os.environ['HERMES_SESSION_SOURCE_EXPLICIT'] = '1'
    os.environ['HERMES_SINGLE_QUERY_SESSION'] = '1'
    with SessionDB(Path(request['profile_home']) / 'state.db') as db:
        agent = AIAgent.__new__(AIAgent)
        agent._session_db, agent._session_db_created = db, False
        agent.session_id, agent.platform, agent.model = 'f7-native-child', 'cli', 'no-inference'
        agent._cached_system_prompt, agent._parent_session_id = '', None
        agent._session_init_model_config = {}
        # The real native method constructs the row, including source-derived cwd.
        agent._ensure_db_session()
        row = db.get_session(agent.session_id)
        first = json.loads(terminal_tool('pwd; /bin/cat base.txt', task_id='f7-new'))
        assert first.get('exit_code') == 0, first
        assert str(Path(request['workdir'])) in first['output'], first
        assert 'F7_BASE' in first['output'], first
        assert row['cwd'] == request['workdir'], row
        # Publish only plugin association; the native DB row above is never edited.
        request['caller_home'] = request['profile_home']  # disposable fixture owns both roles
        status = {**request, 'child_session_id': agent.session_id, 'status': 'completed'}
        core.json_safe_write(run_dir / 'status.json', status)
        core.json_safe_write(run_dir / 'request.json', request)
        os.chdir(request['profile_home'])
        os.environ['TERMINAL_CWD'] = request['profile_home']
        from tools.terminal_scope import set_terminal_scope
        set_terminal_scope(None)  # discard the launch scope before native restore
        target = core.ValidatedProfile('fixture', 'fixture', request['profile_home'])
        retained = core.worktrees.resume(target, agent.session_id, request['origin'], '', core.load_effective_policy())
        assert retained['workdir'] == request['workdir']
        # Native restore without --in or a caller-supplied workdir.
        CLISessionMixin._restore_session_cwd(SimpleNamespace(), row, quiet=True)
        second = json.loads(terminal_tool('pwd; /bin/cat base.txt', task_id='f7-resume'))
        assert second.get('exit_code') == 0 and 'F7_BASE' in second['output'], second
        assert os.getcwd() == request['workdir']
        print(json.dumps({'source': row['source'], 'native_cwd': row['cwd'],
                          'new_terminal': first, 'resume_terminal': second,
                          'resume_workdir_omitted': True, 'provider_called': False}))


if __name__ == '__main__':
    main()
