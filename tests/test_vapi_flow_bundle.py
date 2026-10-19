import copy
import unittest
from pathlib import Path

from scripts.prepare_vapi_flow_bundle import build_bundle, fingerprint


class VapiFlowBundleTests(unittest.TestCase):
    def snapshot(self):
        return {'assistant': {'id': 'assistant-test', 'updatedAt': '2026-10-19T12:00:00Z',
            'voice': {'voiceId': 'unchanged'}, 'hooks': [], 'silenceTimeoutSeconds': 241,
            'model': {'provider': 'openai', 'model': 'gpt-5.4-mini', 'temperature': 0.2,
                'messages': [{'role': 'system', 'content': 'previous'}],
                'toolIds': ['search', 'handoff', 'transfer', 'end']}},
            'tooldefs': [
                {'id': 'search', 'type': 'function', 'function': {'name': 'search_providers'}},
                {'id': 'handoff', 'type': 'function', 'function': {'name': 'handoff_human'}},
                {'id': 'transfer', 'type': 'transferCall', 'function': {'name': 'transfer_call_tool_PB'},
                 'destinations': [{'message': 'Transfer announcement'}]},
                {'id': 'end', 'type': 'endCall', 'function': {'name': 'end_call_tool'}}]}

    def test_patch_preserves_unrelated_settings_and_rollback_restores_touched_fields(self):
        snapshot = self.snapshot()
        snapshot['assistant'].update({'transcriber': {'provider': 'unchanged'},
            'keypadInputPlan': {'enabled': True, 'delimiters': ['#']},
            'maxDurationSeconds': 600})
        before = copy.deepcopy(snapshot)
        bundle = build_bundle(snapshot, 'new prompt')
        self.assertEqual(before, snapshot)
        self.assertEqual(before['assistant']['model'], bundle['rollback']['model'])
        applied = {**before['assistant'], **bundle['desired']}
        self.assertEqual(before['assistant']['voice'], applied['voice'])
        self.assertEqual('gpt-5.4-mini', applied['model']['model'])
        self.assertEqual(0.2, applied['model']['temperature'])
        self.assertEqual(['search', 'transfer', 'end'], applied['model']['toolIds'])
        self.assertEqual(before['assistant'], {**applied, **bundle['rollback']})
        self.assertEqual({'model', 'hooks', 'silenceTimeoutSeconds'}, set(bundle['desired']))
        self.assertEqual(set(bundle['desired']), set(bundle['rollback']))
        self.assertEqual(90, applied['silenceTimeoutSeconds'])
        self.assertEqual(before['tooldefs'], snapshot['tooldefs'])

    def test_idle_hooks_are_exact_bounded_and_reset_only_on_user_speech(self):
        bundle = build_bundle(self.snapshot(), 'new prompt')
        hooks = bundle['desired']['hooks']
        self.assertEqual(2, len(hooks))
        for hook, seconds, message in zip(hooks, (15, 45), (
                'Você ainda está na linha?', 'Estou aguardando sua resposta para continuar.')):
            self.assertEqual('customer.speech.timeout', hook['on'])
            self.assertEqual({'timeoutSeconds': seconds, 'triggerMaxCount': 1,
                              'triggerResetMode': 'onUserSpeech'}, hook['options'])
            self.assertEqual([{'type': 'say', 'exact': message}], hook['do'])

    def test_unrelated_hooks_are_preserved_and_regeneration_does_not_duplicate_idle_hooks(self):
        snapshot = self.snapshot()
        unrelated = {'on': 'assistant.speech.interrupted', 'do': [{'type': 'say', 'exact': 'Certo.'}]}
        snapshot['assistant']['hooks'] = [unrelated]
        before = copy.deepcopy(snapshot)
        bundle = build_bundle(snapshot, 'new prompt')
        self.assertEqual(unrelated, bundle['desired']['hooks'][0])
        self.assertEqual([unrelated], bundle['rollback']['hooks'])
        self.assertEqual(before, snapshot)
        snapshot['assistant'].update(copy.deepcopy(bundle['desired']))
        repeated = build_bundle(snapshot, 'new prompt')
        self.assertEqual(bundle['desired'], repeated['desired'])
        self.assertEqual([], repeated['manifest']['changed_fields'])
        self.assertEqual(['model', 'hooks', 'silenceTimeoutSeconds'],
                         repeated['manifest']['touched_fields'])
        self.assertEqual(repeated['manifest']['expected_fields_sha256'],
                         repeated['manifest']['desired_fields_sha256'])

    def test_manifest_reports_only_the_values_that_actually_change(self):
        snapshot = self.snapshot()
        initial = build_bundle(snapshot, 'new prompt')
        self.assertEqual(['model.messages', 'model.toolIds', 'hooks', 'silenceTimeoutSeconds'],
                         initial['manifest']['changed_fields'])
        snapshot['assistant'].update(copy.deepcopy(initial['desired']))
        snapshot['assistant']['model']['messages'] = [{'role': 'system', 'content': 'old'}]
        changed = build_bundle(snapshot, 'new prompt')
        self.assertEqual(['model.messages'], changed['manifest']['changed_fields'])
        self.assertEqual({'model', 'hooks', 'silenceTimeoutSeconds'},
                         set(changed['manifest']['expected_fields_sha256']))

    def test_incompatible_timeout_hooks_and_malformed_hooks_fail_closed(self):
        for hooks in (None, {}, ['bad'], [{'on': 'customer.speech.timeout',
                'options': {'timeoutSeconds': 30}, 'do': [{'type': 'endCall'}]}]):
            with self.subTest(hooks=hooks):
                snapshot = self.snapshot()
                snapshot['assistant']['hooks'] = hooks
                with self.assertRaises(ValueError):
                    build_bundle(snapshot, 'new prompt')

    def test_absent_hooks_have_explicit_empty_rollback_and_presence_aware_precondition(self):
        snapshot = self.snapshot()
        del snapshot['assistant']['hooks']
        bundle = build_bundle(snapshot, 'new prompt')
        self.assertEqual([], bundle['rollback']['hooks'])
        self.assertEqual({'hooks': 'explicit_empty_list'}, bundle['manifest']['absent_field_restoration'])
        self.assertEqual(fingerprint({'present': False}),
                         bundle['manifest']['expected_fields_sha256']['hooks'])
        explicit = self.snapshot()
        other = build_bundle(explicit, 'new prompt')
        self.assertNotEqual(bundle['manifest']['expected_fields_sha256']['hooks'],
                            other['manifest']['expected_fields_sha256']['hooks'])

    def test_missing_or_invalid_silence_timeout_never_guesses_a_default(self):
        for value in ('missing', None, True, 0, '241'):
            with self.subTest(value=value):
                snapshot = self.snapshot()
                if value == 'missing':
                    del snapshot['assistant']['silenceTimeoutSeconds']
                else:
                    snapshot['assistant']['silenceTimeoutSeconds'] = value
                with self.assertRaises(ValueError):
                    build_bundle(snapshot, 'new prompt')

    def test_updated_at_and_presence_aware_hashes_cover_every_touched_field(self):
        snapshot = self.snapshot()
        bundle = build_bundle(snapshot, 'new prompt')
        manifest = bundle['manifest']
        self.assertEqual(snapshot['assistant']['updatedAt'], manifest['expected_updated_at'])
        for field in bundle['desired']:
            self.assertEqual(fingerprint({'present': True, 'value': snapshot['assistant'][field]}),
                             manifest['expected_fields_sha256'][field])
            self.assertEqual(fingerprint({'present': True, 'value': bundle['desired'][field]}),
                             manifest['desired_fields_sha256'][field])
        self.assertEqual(manifest['desired_fields_sha256'],
                         manifest['rollback_preconditions']['expected_fields_sha256'])
        self.assertEqual('require_reviewed_post_publication_updatedAt',
                         manifest['rollback_preconditions']['updated_at_policy'])
        self.assertEqual('local_only', manifest['publication_status'])

    def test_missing_snapshot_revision_fails_closed(self):
        for updated_at in (None, ''):
            snapshot = self.snapshot()
            snapshot['assistant']['updatedAt'] = updated_at
            with self.assertRaises(ValueError):
                build_bundle(snapshot, 'new prompt')

    def test_bundle_and_prompt_versions_match_the_mitigation(self):
        prompt = (Path(__file__).resolve().parents[1]
                  / 'app/tenants/pbsaude/vapi/prompt.md').read_text()
        bundle = build_bundle(self.snapshot(), prompt)
        self.assertEqual('pbsaude-flow-v18-mitigation', bundle['manifest']['version'])
        self.assertIn('fluxo v18', prompt.splitlines()[0])

    def test_recovery_prompt_uses_supplied_question_and_waits_for_real_new_reply(self):
        prompt = (Path(__file__).resolve().parents[1]
                  / 'app/tenants/pbsaude/vapi/prompt.md').read_text()
        self.assertIn('data.requires_user_turn=true', prompt)
        self.assertIn('data.clarification_question', prompt)
        self.assertIn('exatamente a pergunta', prompt)
        self.assertIn('NOVA resposta real', prompt)
        self.assertIn('não repita a oferta', prompt)
        self.assertIn('último campo ou exame concreto', prompt)

    def test_prompt_terminal_and_active_search_actions_precede_handoff_and_collection(self):
        prompt = (Path(__file__).resolve().parents[1]
                  / 'app/tenants/pbsaude/vapi/prompt.md').read_text()
        recovery = prompt[prompt.index('O retorno pode estar diretamente'):prompt.index('## Apresentação')]
        stop = recovery.index('- `stop`')
        wait = recovery.index('- `wait_current_search`')
        handoff = recovery.index('- `offer_handoff`')
        generic_non_retryable = recovery.index('`retryable=false`')
        collect = recovery.index('- `collect_cpf`')
        self.assertLess(stop, wait)
        self.assertLess(wait, handoff)
        self.assertLess(wait, generic_non_retryable)
        self.assertLess(handoff, collect)
        stop_rule = recovery[stop:wait]
        wait_rule = recovery[wait:handoff]
        self.assertIn('não ofereça atendimento humano', stop_rule)
        self.assertIn('não ofereça atendimento humano', wait_rule)

    def test_missing_native_announcement_fails_closed(self):
        snapshot = self.snapshot()
        snapshot['tooldefs'][2]['destinations'] = []
        with self.assertRaises(ValueError): build_bundle(snapshot, 'new')

    def test_unknown_model_fields_and_missing_tool_definition_require_review(self):
        snapshot = self.snapshot()
        snapshot['assistant']['model']['credentialId'] = 'must-not-copy'
        with self.assertRaises(ValueError): build_bundle(snapshot, 'new')
        snapshot = self.snapshot()
        snapshot['tooldefs'].pop()
        with self.assertRaises(ValueError): build_bundle(snapshot, 'new')

    def test_prompt_forbids_partial_cpf_confirmation_during_recovery(self):
        prompt = (Path(__file__).resolve().parents[1]
                   / 'app/tenants/pbsaude/vapi/prompt.md').read_text()
        recovery = prompt[prompt.index('`collect_cpf`'):prompt.index('`upstream_code=USER_TURN_REQUIRED`')]
        self.assertIn('sufixo/últimos dígitos', recovery)
        self.assertIn('11 dígitos no teclado', recovery)
        self.assertIn('terminados em `#`', recovery)
