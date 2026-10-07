"""Strict readback of the existing finite development-test PowerMgr override.

This never changes policy or proves default suspend/resume behavior by itself.
"""
import re


def power_timeout(text):
    rows = [line for line in text.splitlines() if line.startswith('ScreenOffTime:')]
    match = (re.fullmatch(r'ScreenOffTime: Timeout=(\d+)ms(?:  OverrideTimeout=(\d+)ms)?', rows[0])
             if len(rows) == 1 else None)
    if (match is None or int(match[1]) <= 0 or (match[2] and int(match[2]) <= 0)):
        raise ValueError('one actual positive PowerMgr screen timeout state required')
    return {'base_ms': int(match[1]), 'override_ms': int(match[2]) if match[2] else None}


def verify_policy_states(before, setup, restored):
    for state in (before, setup, restored):
        if (not isinstance(state, dict) or set(state) != {'base_ms', 'override_ms'} or
                type(state['base_ms']) is not int or state['base_ms'] <= 0 or
                (state['override_ms'] is not None and (type(state['override_ms']) is not int or
                                                       state['override_ms'] <= 0))):
            raise ValueError('actual positive integer PowerMgr policy readbacks required')
    if before['override_ms'] is not None:
        raise ValueError('finite test must not replace another client\'s PowerMgr override')
    if (setup != dict(before, override_ms=86400000) or
            type(setup.get('override_ms')) is not int or restored != before):
        raise ValueError('actual finite timeout or original PowerMgr policy was not restored')


def verify_restoration(reply, before, setup, restored):
    """Accept an already-restored nested test only when the real policy agrees."""
    verify_policy_states(before, setup, restored)
    response = reply.strip()
    if response == 'Restore screen off time':
        return 'restored_by_suite'
    if response == 'Restore screen off time failed' and restored == before:
        return 'already_restored_by_nested_test'
    raise ValueError('real PowerMgr rejected screen timeout restoration')
