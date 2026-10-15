"""Session summary/migration and destructive-action guards, using isolated databases."""
import sys
import json
from pathlib import Path
from contextlib import contextmanager
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from memory.sqlite_memory import SessionMemory


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
