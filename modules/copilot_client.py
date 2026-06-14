#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  GitHub Copilot API Client                                      ║
║  Integration für SuperMegaBot + RudiBot Eternal                 ║
║  Nutzt GitHub Token für Copilot Chat + Inline Completions     ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, json, urllib.request, urllib.error, logging
from pathlib import Path

log = logging.getLogger('CopilotClient')

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
COPILOT_ENABLED = os.getenv('COPILOT_ENABLED', 'true').lower() == 'true'
COPILOT_MODEL = os.getenv('COPILOT_MODEL', 'gpt-4o-copilot')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
CLAUDE_FALLBACK_MODEL = 'claude-haiku-4-5-20251001'

BASE_HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
}

_COPILOT_QUOTA_EXCEEDED = False


def _claude_fallback(messages: list[dict]) -> str | None:
    """Call Claude API when Copilot quota is exhausted."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        payload = json.dumps({
            'model': CLAUDE_FALLBACK_MODEL,
            'max_tokens': 2048,
            'messages': [m for m in messages if m['role'] != 'system'],
            'system': next((m['content'] for m in messages if m['role'] == 'system'), None),
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            return data['content'][0]['text']
    except Exception as e:
        log.error('Claude fallback failed: %s', e)
        return None


def _request(path, data=None, method='GET'):
    """Generic GitHub API request."""
    global _COPILOT_QUOTA_EXCEEDED
    if not GITHUB_TOKEN or not COPILOT_ENABLED:
        return None
    url = f'https://api.github.com{path}'
    try:
        req = urllib.request.Request(url, headers=BASE_HEADERS, method=method)
        if data:
            req.data = json.dumps(data).encode('utf-8')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 402:
            _COPILOT_QUOTA_EXCEEDED = True
            log.warning('Copilot spend limit reached — switching to Claude fallback')
        else:
            log.error('GitHub API %s: HTTP %s - %s', path, e.code, e.reason)
        return None
    except Exception as e:
        log.error('GitHub API %s: %s', path, e)
        return None


def chat_completion(messages, model=None):
    """
    Copilot Chat Completion via GitHub API — falls back to Claude on 402.
    messages: list of {"role": "user|assistant|system", "content": "..."}
    """
    if _COPILOT_QUOTA_EXCEEDED or not COPILOT_ENABLED:
        log.info('Using Claude fallback for chat_completion')
        return _claude_fallback(messages)
    payload = {
        'model': model or COPILOT_MODEL,
        'messages': messages,
        'temperature': 0.3,
        'max_tokens': 2048,
    }
    result = _request('/copilot/chat/completions', data=payload, method='POST')
    if result and 'choices' in result:
        return result['choices'][0]['message']['content']
    # _request returned None — may have set _COPILOT_QUOTA_EXCEEDED
    if _COPILOT_QUOTA_EXCEEDED:
        return _claude_fallback(messages)
    return None


def inline_suggestion(code_context, language='javascript', filename=None):
    """
    Get inline code suggestion for a given context.
    code_context: { 'prefix': 'code before cursor', 'suffix': 'code after cursor' }
    """
    if not COPILOT_ENABLED:
        return None
    payload = {
        'prompt': code_context.get('prefix', ''),
        'suffix': code_context.get('suffix', ''),
        'language': language,
        'max_tokens': 256,
        'temperature': 0.2,
    }
    if filename:
        payload['filename'] = filename
    result = _request('/copilot/code_completion', data=payload, method='POST')
    if result and 'completion' in result:
        return result['completion']
    return None


def explain_code(code_snippet, language='javascript'):
    """Ask Copilot to explain a code snippet."""
    messages = [
        {'role': 'system', 'content': f'You are a helpful coding assistant. Explain the following {language} code concisely in German or English as requested.'},
        {'role': 'user', 'content': f'Explain this code:\n```{language}\n{code_snippet}\n```'},
    ]
    return chat_completion(messages)


def fix_code(code_snippet, error_message=None, language='javascript'):
    """Ask Copilot to fix/improve code."""
    prompt = f'Fix or improve this {language} code. Return ONLY the corrected code block, no explanations.'
    if error_message:
        prompt += f'\nError: {error_message}'
    messages = [
        {'role': 'system', 'content': 'You are a senior developer. Output only corrected code.'},
        {'role': 'user', 'content': f'{prompt}\n\n```{language}\n{code_snippet}\n```'},
    ]
    return chat_completion(messages)


def generate_tests(code_snippet, language='javascript', framework='jest'):
    """Generate unit tests for a code snippet."""
    messages = [
        {'role': 'system', 'content': f'Generate {framework} unit tests for the given {language} code. Output only the test code.'},
        {'role': 'user', 'content': f'Generate tests for:\n```{language}\n{code_snippet}\n```'},
    ]
    return chat_completion(messages)


def summarize_errors(log_text):
    """Summarize error logs and suggest fixes."""
    messages = [
        {'role': 'system', 'content': 'You are DevOps. Summarize errors concisely and suggest 3 fixes. Use bullet points.'},
        {'role': 'user', 'content': f'Analyze these logs:\n{log_text[:4000]}'},
    ]
    return chat_completion(messages)


# ── Rudibot Eternal Guardian Integration ──────────────────────────────────
def guardian_ai_suggest(service_name, error_log, last_fix=None):
    """
    Called by eternal_guardian.py when a service fails.
    Returns: { 'action': 'restart|kill|ignore', 'reason': '...', 'code_fix': '...' }
    """
    prompt = f"""Service '{service_name}' failed.
Error log:
{error_log[:2000]}

Last fix applied: {last_fix or 'none'}

Respond ONLY in JSON:
{{"action": "restart|kill|ignore", "reason": "short reason", "code_fix": "if applicable, fixed code or null"}}"""
    messages = [
        {'role': 'system', 'content': 'You are an AI DevOps agent. Return ONLY valid JSON.'},
        {'role': 'user', 'content': prompt},
    ]
    raw = chat_completion(messages)
    if not raw:
        return None
    try:
        # Extract JSON from markdown code block if present
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0]
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0]
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        log.error(f'Invalid JSON from Copilot: {raw[:200]}')
        return None


# ── SuperMegaBot Orchestrator Integration ─────────────────────────────────
def orchestrator_plan(task_description, available_services):
    """
    Called by mega_orchestrator.py to plan multi-step tasks.
    Returns list of steps with service assignments.
    """
    svc_list = ', '.join(available_services)
    prompt = f"""Task: {task_description}
Available services: {svc_list}

Create a step-by-step execution plan. Respond ONLY in JSON array:
[{{"step": 1, "service": "service_name", "action": "...", "params": {{}}}}]"""
    messages = [
        {'role': 'system', 'content': 'You are a task orchestrator. Return ONLY valid JSON array.'},
        {'role': 'user', 'content': prompt},
    ]
    raw = chat_completion(messages)
    if not raw:
        return None
    try:
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0]
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0]
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        log.error(f'Invalid JSON from Copilot: {raw[:200]}')
        return None


if __name__ == '__main__':
    # Quick test
    print('Copilot Client ready.')
    print(f'Token present: {bool(GITHUB_TOKEN)}')
    print(f'Enabled: {COPILOT_ENABLED}')
