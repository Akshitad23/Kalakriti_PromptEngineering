"""Offline deployment smoke checks; never touches the event database."""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
os.environ['GROQ_API_KEY'] = ''
os.environ['ADMIN_PASSWORD'] = 'smoke-test-only'

with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1], ignore_cleanup_errors=True) as tmp:
    import logger_db
    logger_db.DB_PATH = Path(tmp) / 'smoke.db'
    import app as game
    import ai_client
    from config import CATEGORIES
    client = game.app.test_client()
    def post(path, **data):
        return client.post('/api/' + path, json=data)
    assert client.get('/').status_code == 200
    assert client.get('/app.js').status_code == 200
    assert client.get('/style.css').status_code == 200
    assert client.get('/api/health').json['status'] == 'ok'
    assert client.get('/api/admin/export').status_code == 401
    assert post('debug/keywords', message='test').status_code == 401
    assert post('session/start', team_id='').status_code == 400
    assert post('session/start', team_id='SMOKE').status_code == 200
    assert post('session/start', team_id='SMOKE').status_code == 400
    assert post('chat', team_id='SMOKE', message='x' * 1001).status_code == 400
    assert post('hint', team_id='SMOKE').json['already_used'] is False
    assert post('hint', team_id='SMOKE').json['already_used'] is True
    for component in ('word', 'numbers', 'symbol'):
        category = next(v for v in CATEGORIES.values() if v.get('component') == component)
        result = post('chat', team_id='SMOKE', message=category['keywords'][0])
        assert result.status_code == 200, result.json
        if result.json['hint_revealed']:
            assert result.json['hint_revealed']['hint_text'] in result.json['aria_reply']
    session = game.session_manager.get_session('SMOKE')
    assert session.all_revealed()
    assert post('confirm', team_id='SMOKE', assembled_password=session.password).json['correct']
    assert post('chat', team_id='SMOKE', message='hello').status_code == 400
    post('session/start', team_id='PARTIAL')
    partial = game.session_manager.get_session('PARTIAL')
    partial.components_revealed.update(('word', 'numbers', 'symbol'))
    for _ in range(3):
        result = post('confirm', team_id='PARTIAL', assembled_password='incorrect')
    assert result.json['max_attempts_hit'] and not partial.success
    post('session/start', team_id='TIMEOUT')
    post('session/timeout', team_id='TIMEOUT')
    assert post('chat', team_id='TIMEOUT', message='hello').status_code == 400
    for effect in ('memory_wipe', 'free_fragment'):
        team = effect.upper()
        post('session/start', team_id=team)
        assert post('challenge/effect', team_id=team, effect=effect).status_code == 400
        session = game.session_manager.get_session(team)
        session.start_time = datetime.now() - timedelta(seconds=301)
        session.history.append({'role': 'user', 'content': 'hello'})
        assert post('challenge/effect', team_id=team, effect=effect).status_code == 200
        assert post('challenge/effect', team_id=team, effect=effect).status_code == 400
        if effect == 'memory_wipe':
            assert not session.history
        else:
            assert len(session.components_revealed) == 1
    with patch.object(ai_client, '_is_client_ready', return_value=True), patch.object(ai_client, '_call_with_timeout', return_value=(None, False)):
        reply, fallback = ai_client.get_aria_response('hello', [], 1, hint_text='TEST HINT')
        assert fallback and 'TEST HINT' in reply['reply']
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ARIA ONLINE. Access denied."))])
    with patch.object(ai_client, '_client', mock_client), patch.object(ai_client, 'GROQ_MODEL_PERSONA', 'openai/gpt-oss-120b'):
        reply, fallback = ai_client.get_aria_response('hello', [], 0)
        assert not fallback and reply['reply'] == 'ARIA ONLINE. Access denied.'
        params = mock_client.chat.completions.create.call_args.kwargs
        assert params['model'] == 'openai/gpt-oss-120b'
        assert params['reasoning_effort'] == 'low' and params['reasoning_format'] == 'hidden'
        assert params['max_completion_tokens'] == 1024 and 'max_tokens' not in params
    export = client.get('/api/admin/export', headers={'X-Admin-Key': 'smoke-test-only'})
    assert export.status_code == 200 and 'text/csv' in export.content_type
    assert 'SMOKE' in export.text
    assert client.get('/api/admin/export?key=smoke-test-only').status_code == 200
    game.ADMIN_PASSWORD = ''
    assert client.get('/api/admin/export?key=').status_code == 401
print('PASS: static assets, health, sessions, offline hints/chat, confirmation limits, timeout closure, challenge effects, fallback and admin CSV')
