import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_gym import fixture, good_assessment, gym


class ReviewTests(unittest.TestCase):
    def completed(self, state, cid='first'):
        gym.start(fixture(cid), state)
        gym.event(state['active'], 'answer', 'A concrete design with an invariant')
        return gym.finish(state, good_assessment(state['active']), 'completed')

    def test_pending_assessment_does_not_update_ability(self):
        state = gym.fresh()
        result = self.completed(state)
        self.assertEqual(result['status'], 'review_pending')
        self.assertEqual(state['profile']['reviewed_sessions'], 0)
        self.assertTrue(all(not v for v in state['profile']['dimension_observations'].values()))
        with self.assertRaisesRegex(ValueError, 'pending review'):
            gym.start(fixture('second'), state)
        gym.resolve_review(state, 'skipped', 'Player requests next game without further discussion')
        self.assertEqual(state['profile']['reviewed_sessions'], 1)
        self.assertEqual(state['history'][0]['review_revisions'][0]['disposition'], 'skipped')

    def test_revised_original_evidence_and_audit(self):
        state = gym.fresh()
        self.completed(state)
        gym.rebuttal(state, 'The stated constraint already permits my design')
        replacement = copy.deepcopy(state['history'][0]['assessment'])
        replacement['dimensions']['tradeoff_reasoning']['score'] = 4
        result = gym.resolve_review(state, 'revised', 'Original answer did justify its cost', replacement)
        self.assertEqual(result['revisions'][0]['previous']['dimensions']['tradeoff_reasoning']['score'], 3)
        self.assertEqual(result['assessment']['dimensions']['tradeoff_reasoning']['score'], 4)
        self.assertEqual(result['assessment']['dimensions']['tradeoff_reasoning']['evidence_phase'], 'in-game')
        with self.assertRaisesRegex(ValueError, 'already resolved'):
            gym.resolve_review(state, 'accepted', 'again')

    def test_faulty_rebuttal_can_be_upheld_with_reason(self):
        state = gym.fresh()
        self.completed(state)
        old = copy.deepcopy(state['history'][0]['assessment'])
        gym.rebuttal(state, 'Callbacks never happen even though the contract says they do')
        result = gym.resolve_review(state, 'upheld', 'The original contract guarantees one callback; no new constraint added')
        self.assertEqual(result['assessment'], old)
        self.assertEqual(result['revisions'][0]['disposition'], 'upheld')

    def test_rebuttal_evidence_is_not_independent_game_performance(self):
        state = gym.fresh()
        self.completed(state)
        result = gym.rebuttal(state, 'New rationale after seeing the reference')
        eid = result['events'][-1]['id']
        replacement = copy.deepcopy(result['assessment'])
        for item in replacement['dimensions'].values():
            item.update(event_ids=[eid], score=4, evidence_phase='in-game')
        gym.resolve_review(state, 'revised', 'Credit new reasoning without retroactive independence', replacement)
        self.assertTrue(all(v['evidence_phase'] == 'post-review' for v in state['history'][0]['assessment']['dimensions'].values()))
        self.assertTrue(all(not v for v in state['profile']['dimension_observations'].values()))

    def test_uncertain_requires_explicit_replacement(self):
        state = gym.fresh()
        self.completed(state)
        with self.assertRaises(ValueError):
            gym.resolve_review(state, 'uncertain', 'Not enough evidence')
        replacement = copy.deepcopy(state['history'][0]['assessment'])
        replacement['dimensions']['tradeoff_reasoning'].update(score=None, confidence='low', reason='No real competing constraint')
        gym.resolve_review(state, 'uncertain', 'Neither claim is established', replacement)
        self.assertIsNone(state['history'][0]['assessment']['dimensions']['tradeoff_reasoning']['score'])

    def test_correction_recomputes_unsupported_upgrade_idempotently(self):
        state = gym.fresh()
        state['profile']['current_level'] = 3
        for cid in ('first', 'second'):
            self.completed(state, cid)
            gym.resolve_review(state, 'accepted', 'Review complete')
        self.assertEqual(state['profile']['current_level'], 4)
        sid = state['history'][0]['session_id']
        result = gym.rebuttal(state, 'This rating exceeded the original evidence', sid)
        replacement = copy.deepcopy(result['assessment'])
        for item in replacement['dimensions'].values():
            item.update(score=2)
        gym.resolve_review(state, 'revised', 'Correct overly generous score', replacement, sid)
        for _ in range(3):
            gym.update_profile(state)
            self.assertEqual(state['profile']['current_level'], 3)

    def test_contract_clarification_is_not_domain_confusion(self):
        state = gym.fresh()
        gym.start(fixture(), state)
        for _ in range(4):
            result = gym.event(state['active'], 'clarification', 'What is the callback contract?')
        self.assertFalse(result['switch_suggested'])
        self.assertEqual(result['knowledge_questions'], 0)

    def test_review_of_prior_session_while_another_is_active(self):
        state = gym.fresh()
        self.completed(state)
        sid = state['history'][0]['session_id']
        gym.resolve_review(state, 'accepted', 'Done')
        gym.start(fixture('new'), state)
        active_id = state['active']['session_id']
        with self.assertRaises(ValueError):
            gym.rebuttal(state, 'Ambiguous target')
        gym.rebuttal(state, 'Explicit old target', sid)
        gym.resolve_review(state, 'upheld', 'Explained based on old constraints', session_id=sid)
        self.assertEqual(state['active']['session_id'], active_id)

    def test_cli_review_resumes_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)/'cases'
            cache.mkdir()
            (cache/'test.json').write_text(json.dumps(fixture()))
            def call(*args):
                result = subprocess.run([sys.executable, str(gym.ROOT/'scripts/gym.py'), '--state-dir', tmp, '--cache-dir', str(cache), *args], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            call('start', 'fixture-a')
            call('event', 'answer', '--text', 'Actual design')
            self.assertEqual(call('finish')['status'], 'review_pending')
            self.assertEqual(call('resume')['status'], 'review_pending')
            self.assertEqual(call('select')['status'], 'review_required')
            call('rebuttal', '--text', 'Why is this score uncertain?')
            self.assertEqual(call('review')['events'][-1]['kind'], 'rebuttal')
            call('resolve-review', '--disposition', 'upheld', '--reason', 'No observed evidence, keep null')
            self.assertEqual(call('resume')['status'], 'no_active_session')
            self.assertEqual(call('review')['revisions'][0]['disposition'], 'upheld')

    def test_legacy_profile_retains_baseline_and_can_reopen(self):
        from argparse import Namespace
        state = gym.fresh()
        self.completed(state)
        state['history'][0].pop('review_status')
        state['history'][0].pop('review_revisions')
        state['profile'].pop('level_baseline')
        state['profile'].pop('level_baseline_history_count')
        state['profile']['current_level'] = 4
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'legacy.json').write_text(json.dumps(state))
            args = Namespace(player='legacy', state_dir=tmp)
            with gym.storage(args) as loaded:
                self.assertEqual(loaded['profile']['level_baseline'], 4)
                self.assertEqual(loaded['profile']['level_baseline_history_count'], 1)
                gym.rebuttal(loaded, 'Please reconsider the recorded assessment')
                gym.resolve_review(loaded, 'upheld', 'Existing evidence supports it')
                self.assertEqual(loaded['profile']['current_level'], 4)

    def test_stop_and_switch_do_not_require_extra_acknowledgement(self):
        for reason in ('stopped', 'switched', 'evidence-gap'):
            state = gym.fresh()
            gym.start(fixture(), state)
            result = gym.finish(state, None, reason)
            self.assertEqual(result['review_status'], 'resolved')
            self.assertIsNone(gym.pending_review(state))
            gym.start(fixture('different'), state)

    def test_case_may_have_no_meaningful_alternative(self):
        case = fixture()
        case['reference']['alternatives'] = []
        self.assertEqual(gym.validate(case), [])


if __name__ == '__main__':
    unittest.main()
