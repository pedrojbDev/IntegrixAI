import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

try:
    general = importlib.import_module('scripts.prepare_vapi_general_bundle')
except ModuleNotFoundError:
    general = None


BENEFICIARY_HASH = 'd794c90b183bdb3ec9bc205321de33cd84cbd8d3f7bfd3f58ab3fff97554c278'
PROVIDER_HASH = '96569234308062febd77ca961486dd98e4750cc3105e0051fe691c7368e2e7fd'
RECEIVER = '''rede previous

<!-- PBGERAL_CONTEXT_START -->
Contexto não comprovado: {{pbgeral_pedido_atual}}, {{pbgeral_aps_status}}, {{pbgeral_urgencia_relatada}}.
<!-- PBGERAL_CONTEXT_END -->'''


class GeneralBundleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(general, 'General bundle preparation is not implemented')

    def snapshot(self):
        return {
            'assistant': {
                'id': 'general-test', 'name': 'pbsaude-geral', 'updatedAt': '2026-10-19T12:00:00Z',
                'silenceTimeoutSeconds': 10, 'voice': {'voiceId': 'preserved'},
                'transcriber': {'provider': 'deepgram', 'keyterm': ['APS', 'RATI']},
                'model': {'provider': 'openai', 'model': 'model-preserved',
                          'messages': [{'role': 'system', 'content': 'general previous'}],
                          'toolIds': ['handoff', 'transfer', 'end'],
                          'knowledgeBase': {'provider': 'google', 'fileIds': ['beneficiary', 'provider']}}},
            'rede_assistant': {
                'id': 'rede-test', 'name': 'pbsaude-rede', 'updatedAt': '2026-10-19T11:00:00Z',
                'model': {'provider': 'openai', 'model': 'rede-preserved',
                          'messages': [{'role': 'system', 'content': 'rede previous'}],
                          'toolIds': ['search', 'transfer', 'end']}},
            'tooldefs': [
                {'id': 'handoff', 'updatedAt': 'old', 'orgId': 'private', 'latestVersion': 'v4',
                 'type': 'handoff', 'function': {'name': 'handoff_tool'},
                 'messages': [{'type': 'request-start', 'content': 'Existing announcement', 'blocking': True}],
                 'destinations': [{'type': 'assistant', 'assistantId': 'rede-test',
                                   'description': 'Directory lookup', 'contextEngineeringPlan': {'type': 'none'}}]},
                {'id': 'transfer', 'type': 'transferCall',
                 'function': {'name': 'transfer_call_tool_PB', 'description': 'Old shared description'},
                 'destinations': [{'type': 'sip', 'sipUri': 'sip:operator@example.invalid',
                                   'message': 'Existing human announcement', 'description': 'Old scope',
                                   'transferPlan': {'mode': 'blind-transfer'}}]},
                {'id': 'end', 'type': 'endCall', 'function': {'name': 'end_call_tool'}}],
            'sources': [
                {'id': 'beneficiary', 'name': 'pbgeral.docx', 'status': 'done', 'text_sha256': BENEFICIARY_HASH},
                {'id': 'provider', 'name': 'pbprest.docx', 'status': 'done', 'text_sha256': PROVIDER_HASH}],
            'tenant_assistant_map': {'rede-test': 'pbsaude', 'unrelated': 'tenant-other'},
        }

    def bundle(self, snapshot=None):
        return general.build_bundle(snapshot or self.snapshot(), 'general candidate', RECEIVER)

    def created_tools(self, bundle):
        return [dict(copy.deepcopy(body), id='dedicated-' + key,
                     updatedAt='2026-10-23T12:00:00Z', orgId='private', latestVersion='v1')
                for key, body in bundle['tool_creates'].items()]

    def test_staging_never_emits_ready_general_patch_before_dedicated_tools_exist(self):
        snapshot = self.snapshot(); before = copy.deepcopy(snapshot)
        bundle = self.bundle(snapshot)
        self.assertIsNone(bundle['general']['desired'])
        self.assertEqual('requires_tool_bindings', bundle['manifest']['publication_status'])
        self.assertEqual({'handoff', 'transfer'}, set(bundle['tool_creates']))
        self.assertEqual(before, snapshot)
        for tool in bundle['tool_creates'].values():
            self.assertNotIn('id', tool)
            self.assertNotIn('orgId', tool)
            self.assertNotIn('latestVersion', tool)

    def test_binding_preserves_model_sources_unrelated_fields_and_native_destinations(self):
        snapshot = self.snapshot(); bundle = self.bundle(snapshot); before = copy.deepcopy(bundle)
        bound = general.bind_tools(bundle, self.created_tools(bundle))
        desired = bound['general']['desired']
        self.assertEqual(before, bundle)
        self.assertEqual(['dedicated-handoff', 'dedicated-transfer', 'end'], desired['model']['toolIds'])
        self.assertEqual(snapshot['assistant']['model']['knowledgeBase'], desired['model']['knowledgeBase'])
        self.assertEqual('model-preserved', desired['model']['model'])
        applied = {**snapshot['assistant'], **desired}
        for field in ('voice', 'transcriber'):
            self.assertEqual(snapshot['assistant'][field], applied[field])
        self.assertNotIn('maxDurationSeconds', applied)
        for key in ('handoff', 'transfer'):
            original = next(t for t in snapshot['tooldefs'] if t['id'] == key)
            self.assertEqual(original['destinations'][0].get('message'),
                             bound['tool_creates'][key]['destinations'][0].get('message'))
        self.assertEqual('sip:operator@example.invalid',
                         bundle['tool_creates']['transfer']['destinations'][0]['sipUri'])

    def test_idle_configuration_and_rollback_are_presence_aware(self):
        bundle = self.bundle(); bound = general.bind_tools(bundle, self.created_tools(bundle))
        desired = bound['general']['desired']
        self.assertEqual(90, desired['silenceTimeoutSeconds'])
        self.assertEqual([15, 45], [h['options']['timeoutSeconds'] for h in desired['hooks']])
        self.assertTrue(all(h['options']['triggerMaxCount'] == 1 for h in desired['hooks']))
        self.assertTrue(all(h['options']['triggerResetMode'] == 'onUserSpeech' for h in desired['hooks']))
        self.assertTrue(all(h['do'][0]['type'] == 'say' for h in desired['hooks']))
        restored = {**desired, **bound['general']['rollback']}
        self.assertEqual(10, restored['silenceTimeoutSeconds'])
        self.assertEqual([], restored['hooks'])
        self.assertEqual(self.snapshot()['assistant']['model'], restored['model'])
        self.assertEqual({'hooks': 'explicit_empty_list'}, bound['general']['absent_field_restoration'])

    def test_context_arguments_are_optional_bounded_and_not_evidence(self):
        schema = self.bundle()['tool_creates']['handoff']['function']['parameters']
        props = schema['properties']
        self.assertEqual(['destination'], schema['required'])
        self.assertEqual(['rede-test'], props['destination']['enum'])
        self.assertEqual(160, props['pbgeral_pedido_atual']['maxLength'])
        for key in ('pbgeral_aps_status', 'pbgeral_urgencia_relatada'):
            self.assertEqual(['sim', 'nao', 'nao_informado'], props[key]['enum'])
        self.assertFalse(schema['additionalProperties'])
        self.assertNotIn('cpf', props)
        self.assertEqual({'type': 'none'}, self.bundle()['tool_creates']['handoff']['destinations'][0]['contextEngineeringPlan'])

    def test_receiver_changes_only_system_prompt_and_retains_baseline_without_context(self):
        snapshot = self.snapshot(); bundle = self.bundle(snapshot)
        desired = bundle['receiver']['desired']
        self.assertEqual({'model'}, set(desired))
        self.assertEqual(RECEIVER.strip(), desired['model']['messages'][0]['content'])
        self.assertEqual(snapshot['rede_assistant']['model'], bundle['receiver']['rollback']['model'])
        for key in ('provider', 'model', 'toolIds'):
            self.assertEqual(snapshot['rede_assistant']['model'][key], desired['model'][key])
        changed = self.snapshot(); changed['rede_assistant']['model']['messages'][0]['content'] = 'manual edit'
        with self.assertRaises(ValueError): self.bundle(changed)

    def test_mapping_adds_only_general_and_refuses_other_tenant_ownership(self):
        bundle = self.bundle(); desired = bundle['tenant_map']['desired']
        self.assertEqual({**self.snapshot()['tenant_assistant_map'], 'general-test': 'pbsaude'}, desired)
        self.assertEqual(general.fingerprint(desired),
                         bundle['tenant_map']['rollback_preconditions']['expected_sha256'])
        snapshot = self.snapshot(); snapshot['tenant_assistant_map']['general-test'] = 'tenant-other'
        with self.assertRaises(ValueError): self.bundle(snapshot)
        snapshot = self.snapshot(); snapshot['tenant_assistant_map']['rede-test'] = 'tenant-other'
        with self.assertRaises(ValueError): self.bundle(snapshot)

    def test_unreviewed_or_incomplete_sources_are_rejected(self):
        for mutation in ('hash', 'status', 'missing', 'foreign_file'):
            snapshot = self.snapshot()
            if mutation == 'hash': snapshot['sources'][0]['text_sha256'] = '0' * 64
            if mutation == 'status': snapshot['sources'][0]['status'] = 'processing'
            if mutation == 'missing': snapshot['sources'].pop()
            if mutation == 'foreign_file': snapshot['assistant']['model']['knowledgeBase']['fileIds'].append('foreign')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.bundle(snapshot)

    def test_revision_identity_tool_schema_and_idle_conflicts_fail_closed(self):
        for mutation in ('revision', 'identity', 'destination', 'tool_missing', 'secret', 'hook', 'custom_args', 'silence'):
            snapshot = self.snapshot()
            if mutation == 'revision': snapshot['rede_assistant'].pop('updatedAt')
            if mutation == 'identity': snapshot['assistant']['name'] = 'other'
            if mutation == 'destination': snapshot['tooldefs'][0]['destinations'][0]['assistantId'] = 'foreign'
            if mutation == 'tool_missing': snapshot['tooldefs'].pop()
            if mutation == 'secret': snapshot['assistant']['model']['credentialId'] = 'secret'
            if mutation == 'hook': snapshot['assistant']['hooks'] = [{'on': 'customer.speech.timeout'}]
            if mutation == 'custom_args': snapshot['tooldefs'][0]['function']['parameters'] = {'properties': {'cpf': {}}}
            if mutation == 'silence': snapshot['assistant']['silenceTimeoutSeconds'] = None
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.bundle(snapshot)

    def test_bindings_cannot_reuse_shared_tools_or_alter_reviewed_clone_configuration(self):
        bundle = self.bundle()
        for mutation in ('shared_id', 'receiver_tool_id', 'changed_destination', 'missing', 'duplicate', 'unknown_field'):
            tools = self.created_tools(bundle)
            if mutation == 'shared_id': tools[0]['id'] = 'handoff'
            if mutation == 'receiver_tool_id': tools[0]['id'] = 'search'
            if mutation == 'changed_destination': tools[1]['destinations'][0]['sipUri'] = 'sip:wrong@example.invalid'
            if mutation == 'missing': tools.pop()
            if mutation == 'duplicate': tools[1]['id'] = tools[0]['id']
            if mutation == 'unknown_field': tools[0]['server'] = {'url': 'https://wrong.example.invalid'}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): general.bind_tools(bundle, tools)

    def test_preconditions_cover_all_fields_and_reject_concurrent_change(self):
        bundle = self.bundle(); bound = general.bind_tools(bundle, self.created_tools(bundle))
        for key, source in (('general', 'assistant'), ('receiver', 'rede_assistant')):
            general.verify_preconditions(self.snapshot()[source], bound[key])
            for field in bound[key]['desired']:
                self.assertIn(field, bound[key]['preconditions']['expected_fields_sha256'])
                self.assertIn(field, bound[key]['desired_fields_sha256'])
            changed = copy.deepcopy(self.snapshot()[source]); changed['updatedAt'] = 'concurrent'
            with self.assertRaises(ValueError): general.verify_preconditions(changed, bound[key])
        changed = self.snapshot()['assistant']; changed['model']['knowledgeBase']['fileIds'] = []
        with self.assertRaises(ValueError): general.verify_preconditions(changed, bound['general'])

    def test_unrelated_hooks_and_tools_are_retained(self):
        snapshot = self.snapshot(); hook = {'on': 'assistant.speech.interrupted', 'do': []}
        snapshot['assistant']['hooks'] = [hook]
        snapshot['assistant']['model']['toolIds'].append('unrelated')
        snapshot['tooldefs'].append({'id': 'unrelated', 'type': 'function', 'function': {'name': 'unrelated'}})
        bundle = self.bundle(snapshot); bound = general.bind_tools(bundle, self.created_tools(bundle))
        self.assertEqual(hook, bound['general']['desired']['hooks'][0])
        self.assertEqual('unrelated', bound['general']['desired']['model']['toolIds'][-1])

    def test_cli_stages_private_files_then_requires_new_output_for_binding(self):
        # Exercise the documented direct-script invocation, without PYTHONPATH.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary); snapshot = self.snapshot()
            snapshot['rede_assistant']['model']['messages'][0]['content'] = (
                general.RECEIVER_PROMPT.read_text().split(general.CONTEXT_START)[0].strip())
            path = private / 'snapshot.json'; path.write_text(json.dumps(snapshot))
            output = private / 'staged'
            command = [str(root / '.venv/bin/python'), str(root / 'scripts/prepare_vapi_general_bundle.py'),
                       str(path), str(output)]
            environment = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
            result = subprocess.run(command, cwd=temporary, env=environment, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(0o700, output.stat().st_mode & 0o777)
            self.assertFalse((output / 'general.desired.json').exists())
            for artifact in output.iterdir():
                self.assertEqual(0o600, artifact.stat().st_mode & 0o777)
            staged = json.loads((output / 'bundle.json').read_text())
            created = private / 'created.json'; created.write_text(json.dumps(self.created_tools(staged)))
            bound = private / 'bound'
            result = subprocess.run(command[:-1] + [str(bound), '--created-tools', str(created)],
                                    cwd=temporary, env=environment, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((bound / 'general.desired.json').is_file())
            original = (output / 'bundle.json').read_bytes()
            repeated = subprocess.run(command, cwd=temporary, env=environment, capture_output=True, text=True)
            self.assertNotEqual(0, repeated.returncode)
            self.assertEqual(original, (output / 'bundle.json').read_bytes())
            self.assertEqual(snapshot, json.loads(path.read_text()))


if __name__ == '__main__':
    unittest.main()
