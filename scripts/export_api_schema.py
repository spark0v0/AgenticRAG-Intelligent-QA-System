"""Export public session contracts without starting services or invoking providers."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from api.main import app

schema = app.openapi()
schema['paths'] = {key: value for key, value in schema['paths'].items() if key.startswith('/api/sessions')}
names = {'SessionSummary', 'SessionList', 'SessionUpdate', 'DeletionResult', 'HTTPValidationError', 'ValidationError'}
schema['components']['schemas'] = {key: value for key, value in schema['components']['schemas'].items() if key in names}
print(json.dumps(schema, ensure_ascii=True))
