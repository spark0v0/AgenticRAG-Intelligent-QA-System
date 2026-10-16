"""Session summary/migration and destructive-action guards, using isolated databases."""
import sys
import json
from pathlib import Path
from contextlib import contextmanager
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from memory.sqlite_memory import SessionMemory
from core.rag_system import AgenticRAGSystem


def test_summary_pagination_search_and_repeatable_migration(tmp_path):
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps({f's-{i}': [{'query': f'question {i}', 'response': 'long answer ' * 1000, 'timestamp': i+1}] for i in range(10)}), encoding='utf-8')
    class TracedMemory(SessionMemory):
        statements = []
        @contextmanager
        def connect(self):
            with super().connect() as db:
                db.set_trace_callback(self.statements.append)
                yield db
    memory = TracedMemory(path)
    memory.statements.clear()
    page = memory.search_sessions('', 0, 3)
    assert page['total'] == 10 and len(page['items']) == 3
    assert len([sql for sql in memory.statements if sql.lstrip().upper().startswith('SELECT')]) == 2
    memory.update_session('s-0', 'Pinned note', True)
    assert memory.list_sessions()[0]['session_title'] == 'Pinned note'
    assert memory.search_sessions('pinned')['total'] == 1
    restored = SessionMemory(path)
    assert restored.list_sessions()[0]['pinned']
    assert len(restored.get_history('s-0', 1)) == 1
    assert json.loads(path.read_text(encoding='utf-8'))['s-0'][0]['query'] == 'question 0'


def test_delete_guards_active_runs_and_removes_records_without_reimport(tmp_path):
    path = tmp_path / 'history.sqlite3'
    memory = SessionMemory(path)
    memory.start_run('r', 's', 'question')
    memory.save_input('r', 's', 'question', [])
    memory.record_event({'run_id': 'r', 'seq': 1, 'type': 'started'})
    with pytest.raises(ValueError, match='正在执行'):
        memory.delete_session('s')
    memory.finish_run('r', 'cancelled', {'answer': 'draft'})
    memory.delete_session('s')
    memory.record_event({'run_id': 'r', 'seq': 2, 'type': 'cancelled'})
    restored = SessionMemory(path)
    assert not restored.list_sessions() and not restored.get_run('r')
    with restored.connect() as db:
        assert db.execute('SELECT count(*) FROM events').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM messages').fetchone()[0] == 0


def test_history_cursor_includes_failed_and_legacy_rounds_without_gaps(tmp_path):
    memory = SessionMemory(tmp_path / 'history.sqlite3')
    # Equal timestamps deliberately exercise the stable secondary keys.
    for index in range(7):
        memory.append_turn('s', {'query': f'legacy-{index}', 'response': 'answer', 'timestamp': 1})
    for index in range(5):
        run = f'r-{index}'
        memory.start_run(run, 's', f'question-{index}', {'knowledge_base_id': 'kb'})
        memory.save_input(run, 's', f'question-{index}', [{'filename': 'fixture.png'}])
        if index % 2:
            memory.finish_run(run, 'cancelled', {'answer': 'unfinished'})
        else:
            memory.complete_run(run, {'answer': 'final'}, {'run_id': run, 'query': f'question-{index}',
                'response': 'final', 'timestamp': 1, 'result': {'source_map': [{'citation_id': 'S1'}]}})
        memory.record_event({'run_id': run, 'session_id': 's', 'seq': 1, 'type': 'started'})
    with memory.connect() as db:
        db.execute("UPDATE runs SET started_at=1 WHERE session_id='s'")
    system = object.__new__(AgenticRAGSystem)
    system.memory = memory
    page = system.get_session_detail('s', 3)
    first_cursor = page['history_page']['next_cursor']
    assert first_cursor
    assert page['runs'][-1]['request'] == {'knowledge_base_id': 'kb'}
    seen = []
    while True:
        ids = [message['id'] for message in page['messages'] if message['role'] == 'user']
        ids += [f"{run['id']}-user" for run in page['runs'] if run['status'] != 'success']
        assert len(ids) <= 3
        seen.extend(ids)
        page_runs = {run['id'] for run in page['runs']}
        assert all(event['run_id'] in page_runs for event in page['trace'])
        for run in page['runs']:
            if run['status'] == 'cancelled':
                assert run['result']['answer'] == 'unfinished' and run['attachments']
        cursor = page['history_page']['next_cursor']
        if not cursor:
            break
        # A new round must not shift the cursor or duplicate an already loaded round.
        if not memory.get_run('new'):
            memory.start_run('new', 's', 'new question')
            memory.finish_run('new', 'error', error='fixture')
        page = system.get_session_detail('s', 3, cursor)
    assert len(seen) == len(set(seen)) == 12
    full = system.get_session_detail('s')
    assert {m['id'] for m in full['messages'] if m['role'] == 'user'} <= set(seen)
    assert len(full['runs']) == 6 and len(full['trace']) == 5
    with pytest.raises(ValueError, match='游标无效'):
        memory.history_page('other-session', 3, first_cursor)
    with pytest.raises(ValueError, match='游标无效'):
        memory.history_page('s', 3, 'invalid!')
