"""Synthetic fixtures exercise mechanics; these are not a shipped question bank."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gym


def fixture(cid='fixture-a', historical=False):
    c = {'id': cid, 'title': 'SECRET_TITLE', 'mode': 'sandbox', 'kind': 'toy',
         'difficulty': 3, 'source': {'repository': None, 'document': 'original teaching simulation',
          'url': None, 'base_commit': None, 'completeness': 'simulated', 'disputed': False, 'outcome_verifiable': False},
         'topics': [cid], 'core_conflict': cid, 'prerequisites': [],
         'learning_objectives': ['tradeoff_reasoning', 'correctness_modeling'],
         'initial_context': {'description': 'Initial known context', 'constraints': [], 'code': None},
         'rounds': [{'stage': str(i), 'challenge': 'Question ' + str(i), 'context': 'FUTURE_SECRET' if i else 'Current',
                     'constraints': [], 'evidence': []} for i in range(3)],
         'evidence': [], 'reference': {'actual_decision': 'SECRET_REFERENCE', 'alternatives': ['a', 'b'],
                   'tradeoffs': ['cost'], 'outcome': 'unverified', 'evidence': []},
         'simplifications': [], 'evaluation': {'rubric': 'architecture-rubric-v1'}}
    if historical:
        c.update(mode='historical-replay', kind='historical')
        c['source'].update(repository='org/project', document='RFC-1', url='https://example.org/SECRET_SOURCE', completeness='selected snapshots')
        c['evidence'] = [{'id': 'e' + str(i), 'url': 'https://example.org/SECRET_EVIDENCE',
                          'date': '2020-01-0' + str(i+1), 'summary': 'fact'} for i in range(3)]
        for i, r in enumerate(c['rounds']):
            r.update(as_of='2020-01-0' + str(i+1), evidence=['e' + str(i)])
        c['reference']['evidence'] = ['e2']
    return c


def good_assessment(active):
    return {'summary': 'Specific observed design reasoning', 'dimensions': {
        d: {'score': 3, 'confidence': 'high', 'assistance': 'independent',
            'reason': 'Explained invariant and alternatives', 'event_ids': [1]} for d in gym.DIMENSIONS}}


class GameTests(unittest.TestCase):
    def test_validation_chronology_and_modes(self):
        self.assertEqual(gym.validate(fixture()), [])
        c = fixture(historical=True)
        self.assertEqual(gym.validate(c), [])
        c['rounds'][0]['evidence'] = ['e2']
        self.assertIn('future evidence in round', gym.validate(c))
        c = fixture()
        c['rounds'] *= 3
        self.assertTrue(gym.validate(c))
        c = fixture()
        c['kind'] = 'historical'
        self.assertIn('kind/mode mismatch', gym.validate(c))

    def test_no_future_and_final_reveal(self):
        state = gym.fresh()
        visible = gym.start(fixture(historical=True), state)
        text = json.dumps(visible)
        for hidden in ('SECRET_TITLE', 'FUTURE_SECRET', 'SECRET_REFERENCE', 'SECRET_SOURCE', 'SECRET_EVIDENCE'):
            self.assertNotIn(hidden, text)
        result = gym.finish(state, None, 'stopped')
        self.assertEqual(result['reference']['actual_decision'], 'SECRET_REFERENCE')
        self.assertTrue(state['history'][0]['reference_revealed'])
        self.assertEqual(state['profile']['completed_sessions'], 0)

    def test_background_is_not_answer_and_never_downgrades(self):
        state = gym.fresh()
        state['profile']['current_level'] = 3
        gym.start(fixture(), state)
        for _ in range(3):
            result = gym.event(state['active'], 'knowledge-question', 'What is this?')
        self.assertTrue(result['switch_suggested'])
        with self.assertRaises(ValueError):
            gym.advance(state['active'])
        gym.finish(state, None, 'switched')
        self.assertEqual(state['profile']['current_level'], 3)

    def test_finite_rounds(self):
        state = gym.fresh()
        gym.start(fixture(), state)
        for i in range(3):
            gym.event(state['active'], 'answer', 'Keep a single owner and compare costs')
            result = gym.advance(state['active'])
        self.assertEqual(result['status'], 'ready_to_finish')
        self.assertEqual(state['active']['round_index'], 2)
        self.assertEqual(gym.advance(state['active'])['status'], 'ready_to_finish')

    def test_resume_preserves_past_constraints_and_rejects_extra_fields(self):
        state = gym.fresh()
        c = fixture()
        c['rounds'][0]['constraints'] = ['first-round invariant']
        gym.start(c, state)
        gym.event(state['active'], 'answer', 'Design based on invariant')
        result = gym.advance(state['active'])
        self.assertEqual(result['previous_rounds'][0]['constraints'], ['first-round invariant'])
        c['rounds'][0]['hidden_answer'] = 'spoiler'
        self.assertIn('round fields must match schema', gym.validate(c))
        c['initial_context']['reference'] = 'spoiler'
        self.assertIn('initial_context fields must match schema', gym.validate(c))

    def test_duplicate_alias_conflict_and_explicit_review(self):
        state = gym.fresh()
        a = fixture(historical=True)
        gym.start(a, state)
        gym.finish(state, None, 'stopped')
        alias = fixture('alias', historical=True)
        self.assertTrue(gym.duplicate_info(alias, state)['exact'])
        b = fixture('b')
        b['core_conflict'] = a['core_conflict']
        self.assertTrue(gym.duplicate_info(b, state)['semantic_proxy'])
        self.assertEqual(gym.select({'b': b}, state, level=3)['status'], 'needs_case')
        self.assertEqual(gym.select({'b': b}, state, level=3, review=True)['practice_type'], 'transfer')
        with self.assertRaises(ValueError):
            gym.start(alias, state)

    def test_upgrade_two_independent_different_cases_only(self):
        state = gym.fresh()
        state['profile']['current_level'] = 3
        for cid in ('one', 'two'):
            gym.start(fixture(cid), state)
            gym.event(state['active'], 'answer', 'Explain design with constraints and costs')
            gym.finish(state, good_assessment(state['active']), 'completed')
            self.assertEqual(state['profile']['current_level'], 3 if cid == 'one' else 4)

    def test_hint_cannot_be_scored_independent(self):
        state = gym.fresh()
        gym.start(fixture(), state)
        gym.event(state['active'], 'hint', 'Consider ownership')
        gym.event(state['active'], 'answer', 'Single owner')
        data = good_assessment(state['active'])
        for item in data['dimensions'].values():
            item['event_ids'] = [2]
        with self.assertRaisesRegex(ValueError, 'independence'):
            gym.assessment(data, state['active'])

    def test_score_requires_real_answer(self):
        state = gym.fresh()
        gym.start(fixture(), state)
        gym.event(state['active'], 'knowledge-question', 'Define mechanism')
        with self.assertRaisesRegex(ValueError, 'design answer'):
            gym.assessment(good_assessment(state['active']), state['active'])

    def test_cli_resume_snapshot_multiplayer_and_transaction_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'cases'
            cache.mkdir()
            path = cache / 'fixture-a.json'
            path.write_text(json.dumps(fixture()), encoding='utf8')
            def call(player, *cmd, success=True):
                result = subprocess.run([sys.executable, str(gym.ROOT/'scripts/gym.py'), '--state-dir', tmp,
                                         '--cache-dir', str(cache), '--player', player, *cmd], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if success else 2, result.stderr)
                return json.loads(result.stdout) if success else result.stderr
            call('alice', 'start', 'fixture-a')
            before = (Path(tmp)/'alice.json').read_text()
            call('alice', 'next', success=False)
            self.assertEqual(before, (Path(tmp)/'alice.json').read_text())
            path.unlink()  # active snapshot survives cache removal
            self.assertEqual(call('alice', 'resume')['current_round']['context'], 'Current')
            self.assertEqual(call('bob', 'resume')['status'], 'no_active_session')
            call('../escape', 'profile', success=False)
            call('alice', 'finish', '--reason', 'stopped')
            self.assertEqual(call('alice', 'resume')['status'], 'no_active_session')


if __name__ == '__main__':
    unittest.main()
