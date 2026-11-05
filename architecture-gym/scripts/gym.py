#!/usr/bin/env python3
"""Architecture Gym: deterministic, dependency-free local game state."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = ('abstraction_discovery', 'change_prediction', 'complexity_management',
              'tradeoff_reasoning', 'correctness_modeling', 'architectural_judgment')


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strings(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def validate(case):
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    check(isinstance(case, dict), 'case must be an object')
    if not isinstance(case, dict):
        return errors
    required = {'id', 'title', 'mode', 'kind', 'difficulty', 'source', 'topics', 'core_conflict',
                'prerequisites', 'learning_objectives', 'initial_context', 'rounds', 'evidence',
                'reference', 'simplifications', 'evaluation'}
    check(set(case) == required, 'case fields must match schema')
    check(bool(re.fullmatch(r'[a-z0-9][a-z0-9-]*', str(case.get('id', '')))), 'invalid id')
    check(isinstance(case.get('title'), str) and bool(case.get('title')), 'title required')
    mode = case.get('mode')
    check(mode in ('sandbox', 'historical-replay'), 'invalid mode')
    check(case.get('kind') in ('toy', 'sandbox', 'historical'), 'invalid kind')
    check((case.get('kind') == 'historical') == (mode == 'historical-replay'), 'kind/mode mismatch')
    level = case.get('difficulty')
    check(type(level) is int and 0 <= level <= 5, 'difficulty must be 0..5')
    for key in ('topics', 'prerequisites', 'learning_objectives'):
        check(strings(case.get(key)), key + ' must be string array')
    check(bool(case.get('topics')), 'topics required')
    check(bool(case.get('core_conflict')), 'core_conflict required')
    objectives = case.get('learning_objectives', [])
    check(isinstance(objectives, list) and bool(objectives) and all(x in DIMENSIONS for x in objectives), 'invalid learning objectives')
    context = case.get('initial_context', {})
    check(isinstance(context, dict), 'initial_context must be object')
    if isinstance(context, dict):
        check(set(context) == {'description', 'constraints', 'code'}, 'initial_context fields must match schema')
        check(bool(context.get('description')) and strings(context.get('constraints')), 'initial context description/constraints required')
        check(context.get('code') is None or isinstance(context.get('code'), str), 'code must be text or null')
    source = case.get('source', {})
    check(isinstance(source, dict), 'source must be object')
    if not isinstance(source, dict):
        source = {}
    for key in ('repository', 'document', 'url', 'base_commit', 'completeness', 'disputed', 'outcome_verifiable'):
        check(key in source, 'source.' + key + ' required')
    check(type(source.get('disputed')) is bool and type(source.get('outcome_verifiable')) is bool, 'source certainty flags must be boolean')
    check(bool(source.get('completeness')), 'source completeness required')
    if source.get('base_commit') is not None:
        check(bool(re.fullmatch(r'[a-fA-F0-9]{40}', str(source['base_commit']))), 'base_commit must be verified full SHA or null')
    evidence = case.get('evidence', [])
    check(isinstance(evidence, list), 'evidence must be array')
    evidence_map = {}
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict):
            errors.append('evidence entry must be object')
            continue
        eid = item.get('id')
        check(isinstance(eid, str) and bool(eid) and eid not in evidence_map, 'invalid/duplicate evidence id')
        if isinstance(eid, str):
            evidence_map[eid] = item
        check(str(item.get('url', '')).startswith('https://'), 'evidence needs https URL')
        check(bool(item.get('summary')), 'evidence summary required')
        try:
            date.fromisoformat(item.get('date', ''))
        except (TypeError, ValueError):
            errors.append('invalid evidence date')
    rounds = case.get('rounds', [])
    check(isinstance(rounds, list) and 3 <= len(rounds) <= 5, 'case must provide 3..5 rounds')
    previous = ''
    for item in rounds if isinstance(rounds, list) else []:
        if not isinstance(item, dict):
            errors.append('round must be object')
            continue
        expected = {'stage', 'challenge', 'context', 'constraints', 'evidence'}
        if mode == 'historical-replay':
            expected.add('as_of')
        check(set(item) == expected, 'round fields must match schema')
        check(bool(item.get('stage')) and bool(item.get('challenge')), 'round stage/challenge required')
        check(isinstance(item.get('context'), str) and strings(item.get('constraints')), 'round context/constraints required')
        refs = item.get('evidence', [])
        check(strings(refs) and all(e in evidence_map for e in refs), 'unknown round evidence')
        if mode == 'historical-replay':
            check(bool(refs), 'historical round needs evidence')
            as_of = item.get('as_of', '')
            try:
                date.fromisoformat(as_of)
                check(as_of >= previous, 'round chronology must be monotonic')
                previous = as_of
                for eid in refs:
                    if eid in evidence_map:
                        check(evidence_map[eid].get('date', '9999') <= as_of, 'future evidence in round')
            except (TypeError, ValueError):
                errors.append('historical round needs valid as_of')
    reference = case.get('reference', {})
    check(isinstance(reference, dict), 'reference must be object')
    if isinstance(reference, dict):
        check(bool(reference.get('actual_decision')) and bool(reference.get('outcome')), 'reference decision/outcome required')
        check(strings(reference.get('alternatives')) and strings(reference.get('tradeoffs')), 'reference alternatives/tradeoffs required')
        refs = reference.get('evidence', [])
        check(strings(refs) and all(e in evidence_map for e in refs), 'unknown reference evidence')
        if mode == 'historical-replay':
            check(bool(refs), 'historical reference needs evidence')
    if mode == 'historical-replay':
        check(bool(source.get('repository')) and bool(source.get('document')) and str(source.get('url', '')).startswith('https://'), 'historical source required')
    else:
        check(not evidence and all(not r.get('evidence') for r in rounds if isinstance(r, dict)), 'simulated cases must not claim historical evidence')
    check(isinstance(case.get('evaluation'), dict) and case['evaluation'].get('rubric') == 'architecture-rubric-v1', 'unsupported rubric')
    simplifications = case.get('simplifications', [])
    check(isinstance(simplifications, list), 'simplifications must be array')
    for item in simplifications if isinstance(simplifications, list) else []:
        check(isinstance(item, dict) and type(item.get('difficulty')) is int and type(level) is int and 0 <= item['difficulty'] < level and bool(item.get('case_id')), 'invalid simplification')
    return errors


def catalog(cache_dir):
    cases = {}
    for path in sorted(Path(cache_dir).expanduser().glob('*.json')):
        case = read_json(path)
        errors = validate(case)
        require(not errors, str(path) + ': ' + '; '.join(errors))
        require(case['id'] not in cases, 'duplicate case id: ' + case['id'])
        cases[case['id']] = case
    for case in cases.values():
        for simpler in case['simplifications']:
            target = cases.get(simpler['case_id'])
            if target is not None:
                require(target['difficulty'] == simpler['difficulty'], 'simplification level mismatch')
                require(bool(set(case['learning_objectives']) & set(target['learning_objectives'])), 'simplification must retain a learning objective')
    return cases


def fingerprint(case):
    return hashlib.sha256(json.dumps(case, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def source_key(case):
    source = case['source']
    if case['mode'] == 'historical-replay':
        # Repository + document identifies the same decision even if its URL changes.
        return (str(source['repository']) + ':' + str(source['document'])).lower().rstrip('/')
    return case['id']


def fresh():
    return {'version': 1, 'profile': {'current_level': 1, 'strengths': [], 'weaknesses': [],
            'recent_case_ids': [], 'topic_exposure': {}, 'hint_dependency': {},
            'completed_sessions': 0, 'last_adjustment_at': 0, 'dimension_observations': {}},
            'history': [], 'active': None}


@contextmanager
def storage(args):
    require(bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', args.player)), 'player must be 1..64 letters/digits/_/-')
    base = Path(args.state_dir).expanduser()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = base / (args.player + '.json')
    lock = base / (args.player + '.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Player state is locked. Check for an active writer before removing stale lock: ' + str(lock))
    os.close(fd)
    try:
        state = read_json(path) if path.exists() else fresh()
        require(state.get('version') == 1, 'unsupported state version')
        yield state
        fd, temp = tempfile.mkstemp(prefix='.' + args.player, dir=base)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    finally:
        lock.unlink()


def duplicate_info(case, state):
    played = state['history'] + ([state['active']] if state['active'] else [])
    exact = any(h['case_id'] == case['id'] or h['source_key'] == source_key(case) for h in played)
    recent = played[-3:]
    similar = any(h['core_conflict'] == case['core_conflict'] for h in recent)
    overlap = sum(len(set(h['topics']) & set(case['topics'])) for h in recent)
    return {'exact': exact, 'semantic_proxy': similar, 'recent_topic_overlap': overlap}


def select(cases, state, level=None, review=False):
    level = state['profile']['current_level'] if level is None else level
    ranked = []
    for case in cases.values():
        dup = duplicate_info(case, state)
        # Never silently reuse an exposed decision or repeat a recent design conflict.
        if (dup['exact'] or dup['semantic_proxy']) and not review:
            continue
        if abs(case['difficulty'] - level) > 1:
            continue
        targets = set(case['learning_objectives']) & set(state['profile']['weaknesses'])
        rank = (dup['exact'], dup['semantic_proxy'], abs(case['difficulty'] - level),
                dup['recent_topic_overlap'], -len(targets), case['id'])
        ranked.append((rank, case, dup))
    if not ranked:
        return {'status': 'needs_case', 'target_level': level,
                'avoid_case_ids': [h['case_id'] for h in state['history']],
                'avoid_source_keys': [h['source_key'] for h in state['history']],
                'avoid_recent_conflicts': [h['core_conflict'] for h in state['history'][-3:]],
                'target_dimensions': state['profile']['weaknesses'],
                'instruction': 'Build a new case through isolated source discovery; review requires player agreement.'}
    _, case, dup = min(ranked, key=lambda x: x[0])
    return {'status': 'selected', 'case_id': case['id'], 'difficulty': case['difficulty'],
            'mode': case['mode'], 'kind': case['kind'], 'duplicates': dup,
            'practice_type': 'review' if dup['exact'] else 'transfer' if dup['semantic_proxy'] else 'new'}


def view(active):
    case = active['snapshot']
    idx = active['round_index']
    current = case['rounds'][idx]
    # No source metadata, title, reference, future rounds, or source URLs reach Coach.
    return {'status': 'active', 'session_id': active['session_id'], 'case_id': case['id'],
            'mode': case['mode'], 'kind': case['kind'], 'difficulty': case['difficulty'],
            'round': idx + 1, 'round_limit': len(case['rounds']),
            'initial_context': case['initial_context'],
            'current_round': {k: v for k, v in current.items() if k in ('stage', 'challenge', 'context', 'constraints', 'as_of')},
            'previous_rounds': [{k: v for k, v in r.items() if k in ('stage', 'challenge', 'context', 'constraints', 'as_of')}
                                for r in case['rounds'][:idx]],
            'evidence_available': bool(current['evidence']),
            'provenance_note': 'Historical snapshots; source links withheld until debrief.' if case['mode'] == 'historical-replay' else '模拟情景 / Simulation',
            'visible_transcript': active['events'],
            'knowledge_questions': active['knowledge_questions'],
            'switch_suggested': active['knowledge_questions'] >= 3,
            'practice_type': active['practice_type']}


def start(case, state, review=False):
    require(state['active'] is None, 'Resume or finish the active session before starting another')
    dup = duplicate_info(case, state)
    require(review or not (dup['exact'] or dup['semantic_proxy']), 'Duplicate/recent conflict: create another case or get agreement for --allow-review')
    active = {'session_id': uuid.uuid4().hex, 'case_id': case['id'], 'source_key': source_key(case),
              'core_conflict': case['core_conflict'], 'topics': case['topics'],
              'difficulty': case['difficulty'], 'mode': case['mode'], 'started_at': now(),
              'round_index': 0, 'snapshot': case, 'fingerprint': fingerprint(case),
              'events': [], 'knowledge_questions': 0, 'used_hints': [],
              'revealed_rounds': [1], 'reference_revealed': False,
              'practice_type': 'review' if dup['exact'] else 'transfer' if dup['semantic_proxy'] else 'new'}
    state['active'] = active
    return view(active)


def event(active, kind, text):
    require(isinstance(text, str) and bool(text.strip()), 'event text required')
    entry = {'id': len(active['events']) + 1, 'round': active['round_index'] + 1,
             'kind': kind, 'text': text, 'at': now()}
    active['events'].append(entry)
    if kind == 'knowledge-question':
        active['knowledge_questions'] += 1
    elif kind == 'hint':
        active['used_hints'].append(entry['id'])
    return view(active)


def advance(active):
    idx = active['round_index']
    require(any(e['round'] == idx + 1 and e['kind'] == 'answer' for e in active['events']), 'Record a design answer before advancing; a background question is not an answer')
    if idx + 1 >= len(active['snapshot']['rounds']):
        return {'status': 'ready_to_finish', 'round_limit': idx + 1}
    active['round_index'] += 1
    active['revealed_rounds'].append(idx + 2)
    return view(active)


def assessment(data, active):
    require(isinstance(data, dict), 'assessment must be object')
    scores = data.get('dimensions', {})
    require(isinstance(scores, dict) and set(scores) == set(DIMENSIONS), 'provide all six dimensions; use score:null for unobserved')
    for dimension, item in scores.items():
        require(isinstance(item, dict), 'dimension must be object: ' + dimension)
        score = item.get('score')
        require(score is None or (type(score) is int and 0 <= score <= 4), 'score must be null or 0..4')
        require(item.get('confidence') in ('low', 'medium', 'high'), 'confidence required')
        require(item.get('assistance') in ('independent', 'light', 'repeated', 'unobserved'), 'assistance required')
        require(isinstance(item.get('reason'), str) and bool(item['reason'].strip()), 'behavioral reason required')
        ids = item.get('event_ids')
        require(isinstance(ids, list), 'event_ids required')
        events = [e for e in active['events'] if e['id'] in ids]
        require(len(events) == len(set(ids)), 'unknown event id')
        if score is not None:
            require(any(e['kind'] == 'answer' for e in events), 'score needs a recorded design answer')
            require(item['assistance'] != 'unobserved', 'unobserved dimension must have null score')
            if item['assistance'] == 'independent':
                answer_ids = [e['id'] for e in events if e['kind'] == 'answer']
                require(not any(h < max(answer_ids) for h in active['used_hints']), 'independence contradicted by earlier design hint; assess conservatively')
    require(isinstance(data.get('summary'), str), 'assessment summary required')
    return data


def update_profile(state):
    profile = state['profile']
    completed = [h for h in state['history'] if h['completed']]
    profile['completed_sessions'] = len(completed)
    profile['recent_case_ids'] = [h['case_id'] for h in state['history'][-20:]]
    profile['topic_exposure'] = {}
    profile['hint_dependency'] = {}
    for h in state['history']:
        for topic in h['topics']:
            profile['topic_exposure'][topic] = profile['topic_exposure'].get(topic, 0) + 1
        profile['hint_dependency'][h['session_id']] = len(h['used_hints'])
    observations = {d: [] for d in DIMENSIONS}
    for h in completed[-10:]:
        if h['practice_type'] == 'review':
            continue
        for dim, value in h['assessment']['dimensions'].items():
            if value['score'] is not None and value['confidence'] != 'low':
                observations[dim].append({'score': value['score'], 'assistance': value['assistance'], 'case_id': h['case_id']})
    profile['dimension_observations'] = observations
    profile['strengths'] = [d for d, values in observations.items() if len(values) >= 2 and sum(v['score'] for v in values) / len(values) >= 3]
    profile['weaknesses'] = [d for d, values in observations.items() if len(values) >= 2 and sum(v['score'] for v in values) / len(values) < 2]
    recent = completed[-2:]
    if len(recent) < 2 or len(completed) - profile['last_adjustment_at'] < 2:
        return
    if len({h['core_conflict'] for h in recent}) < 2 or any(h['practice_type'] != 'new' for h in recent):
        return
    def strong(h):
        values = [v for v in h['assessment']['dimensions'].values() if v['score'] is not None and v['confidence'] != 'low']
        return (h['difficulty'] >= profile['current_level'] and not h['used_hints'] and
                len(values) >= 4 and all(v['score'] >= 3 and v['assistance'] == 'independent' for v in values))
    if all(strong(h) for h in recent):
        profile['current_level'] = min(5, profile['current_level'] + 1)
        profile['last_adjustment_at'] = len(completed)
    # Background confusion never lowers persistent ability. Consent-based switch uses an override.


def finish(state, data, reason):
    active = state['active']
    require(active is not None, 'No active session')
    if data is None:
        data = {'summary': 'Insufficient evidence; session ended without numerical evaluation.',
                'dimensions': {d: {'score': None, 'confidence': 'low', 'assistance': 'unobserved',
                                   'reason': 'Not assessed', 'event_ids': []} for d in DIMENSIONS}}
    assessment(data, active)
    case = active['snapshot']
    active.update({'ended_at': now(), 'completed': reason == 'completed', 'end_reason': reason,
                   'assessment': data, 'reference_revealed': True})
    state['history'].append(active)
    state['active'] = None
    update_profile(state)
    return {'status': 'finished', 'end_reason': reason, 'reference': case['reference'],
            'source': case['source'], 'evidence': case['evidence'], 'assessment': data,
            'profile': state['profile']}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--player', default='default')
    p.add_argument('--state-dir', default=os.environ.get('ARCH_GYM_STATE_DIR', '~/.local/share/architecture-gym/players'))
    p.add_argument('--cache-dir', default=os.environ.get('ARCH_GYM_CACHE_DIR', '~/.local/share/architecture-gym/cases'))
    sub = p.add_subparsers(dest='command', required=True)
    choose = sub.add_parser('select')
    choose.add_argument('--level', type=int, choices=range(6))
    choose.add_argument('--allow-review', action='store_true')
    start_p = sub.add_parser('start')
    start_p.add_argument('case_id')
    start_p.add_argument('--allow-review', action='store_true')
    sub.add_parser('resume')
    sub.add_parser('profile')
    level_p = sub.add_parser('set-level')
    level_p.add_argument('level', type=int, choices=range(6))
    ev = sub.add_parser('event')
    ev.add_argument('kind', choices=('answer', 'knowledge-question', 'explanation', 'hint', 'challenge', 'coach-note'))
    ev.add_argument('--text', required=True)
    sub.add_parser('next')
    done = sub.add_parser('finish')
    done.add_argument('--assessment', help='JSON file using the documented rubric')
    done.add_argument('--reason', choices=('completed', 'stopped', 'switched', 'evidence-gap'), default='completed')
    dup = sub.add_parser('duplicates')
    dup.add_argument('case_id')
    check = sub.add_parser('validate')
    check.add_argument('path', nargs='?')
    return p


def run(args):
    if args.command == 'validate':
        if args.path:
            errors = validate(read_json(args.path))
            require(not errors, '; '.join(errors))
            return {'valid': True, 'verification': 'structure only; primary evidence and spoilers require Builder review'}
        cases = catalog(args.cache_dir)
        return {'valid': True, 'count': len(cases), 'verification': 'structure only'}
    with storage(args) as state:
        command = args.command
        if command == 'profile':
            return {'profile': state['profile'], 'active_session': state['active']['session_id'] if state['active'] else None}
        if command == 'set-level':
            require(state['active'] is None, 'Set baseline between sessions')
            state['profile']['current_level'] = args.level
            state['profile']['last_adjustment_at'] = state['profile']['completed_sessions']
            return {'profile': state['profile']}
        if command == 'resume':
            return view(state['active']) if state['active'] else {'status': 'no_active_session'}
        if command in ('select', 'start', 'duplicates'):
            if command == 'select' and state['active']:
                return {'status': 'resume_required', 'session_id': state['active']['session_id']}
            cases = catalog(args.cache_dir)
            if command == 'select':
                return select(cases, state, args.level, args.allow_review)
            require(args.case_id in cases, 'Case not found in cache')
            if command == 'duplicates':
                return duplicate_info(cases[args.case_id], state)
            return start(cases[args.case_id], state, args.allow_review)
        require(state['active'] is not None, 'No active session')
        if command == 'event':
            return event(state['active'], args.kind, args.text)
        if command == 'next':
            return advance(state['active'])
        if command == 'finish':
            data = read_json(args.assessment) if args.assessment else None
            return finish(state, data, args.reason)
    raise ValueError('Unsupported command')


def main(argv=None):
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
