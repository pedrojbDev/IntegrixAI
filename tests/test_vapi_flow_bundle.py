import copy
import unittest
from pathlib import Path

from scripts.prepare_vapi_flow_bundle import build_bundle


class VapiFlowBundleTests(unittest.TestCase):
    def snapshot(self):
        return {'assistant': {'id': 'assistant-test', 'voice': {'voiceId': 'unchanged'},
            'model': {'provider': 'openai', 'model': 'gpt-5.4-mini', 'temperature': 0.2,
                'messages': [{'role': 'system', 'content': 'previous'}],
                'toolIds': ['search', 'handoff', 'transfer', 'end']}},
            'tooldefs': [
                {'id': 'search', 'type': 'function', 'function': {'name': 'search_providers'}},
                {'id': 'handoff', 'type': 'function', 'function': {'name': 'handoff_human'}},
                {'id': 'transfer', 'type': 'transferCall', 'function': {'name': 'transfer_call_tool_PB'},
                 'destinations': [{'message': 'Transfer announcement'}]},
                {'id': 'end', 'type': 'endCall', 'function': {'name': 'end_call_tool'}}]}

    def test_only_prompt_and_attachment_change_and_rollback_restores_exact_model(self):
        snapshot = self.snapshot()
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
