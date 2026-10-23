"""Prepare PB Geral changes locally; never perform Vapi requests or deploy.

The private snapshot contains assistant, rede_assistant, tooldefs, sources and
tenant_assistant_map. Sources are metadata plus hashes, not document contents.
Dedicated tool POST bodies are staged first. A final Geral PATCH is emitted
only after --created-tools supplies the complete GET responses for both clones.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.prepare_vapi_flow_bundle import IDLE_HOOKS, fingerprint

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / 'app/tenants/pbsaude/vapi/general/prompt.md'
RECEIVER_PROMPT = ROOT / 'app/tenants/pbsaude/vapi/prompt.md'
VERSION = 'pbsaude-general-v1-hardening'
APPROVED_SOURCES = {
    'pbgeral.docx': 'd794c90b183bdb3ec9bc205321de33cd84cbd8d3f7bfd3f58ab3fff97554c278',
    'pbprest.docx': '96569234308062febd77ca961486dd98e4750cc3105e0051fe691c7368e2e7fd',
}
CONTEXT_START = '<!-- PBGERAL_CONTEXT_START -->'
CONTEXT_END = '<!-- PBGERAL_CONTEXT_END -->'
CONTEXT_FIELDS = ('pbgeral_pedido_atual', 'pbgeral_aps_status', 'pbgeral_urgencia_relatada')
MODEL_FIELDS = {'provider', 'model', 'messages', 'toolIds', 'tools', 'knowledgeBase',
                'temperature', 'maxTokens', 'numFastTurns', 'emotionRecognitionEnabled'}
TOOL_METADATA = {'id', 'createdAt', 'updatedAt', 'orgId', 'latestVersion'}
TOOL_FIELDS = {'type', 'function', 'messages', 'destinations', 'async', 'rejectionPlan'}
HUMAN_DESCRIPTION = (
    'Transfere beneficiários, interessados e prestadores para atendimento humano PB Saúde. '
    'Use em pedido explícito de atendente e diretamente em urgência/emergência operacional '
    'de prestador, conforme a fonte pbprest.docx. Em outras ofertas, aguarde consentimento. '
    'Use também para informação individual indisponível, conflito de fontes ou falha sem '
    'recuperação aceita pelo usuário. Não substitui o handoff de localização de prestadores.'
)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _model(assistant: dict, name: str) -> dict:
    _require(isinstance(assistant, dict) and assistant.get('name') == name,
             'Unexpected assistant identity')
    _require(_string(assistant.get('id')) and _string(assistant.get('updatedAt')),
             'Assistant ID and updatedAt are required')
    model = assistant.get('model')
    _require(isinstance(model, dict) and not (set(model) - MODEL_FIELDS),
             'Unsupported model fields require review')
    _require(not model.get('tools'), 'Inline tools require manual review')
    messages = model.get('messages')
    _require(isinstance(messages, list) and len(messages) == 1
             and isinstance(messages[0], dict) and messages[0].get('role') == 'system'
             and _string(messages[0].get('content')), 'One system message is required')
    ids = model.get('toolIds')
    _require(isinstance(ids, list) and all(_string(i) for i in ids)
             and len(set(ids)) == len(ids), 'Unique attached tool IDs are required')
    return model


def _field_hashes(value: dict, fields) -> dict:
    return {key: fingerprint({'present': True, 'value': value[key]}
                             if key in value else {'present': False}) for key in fields}


def _change(assistant: dict, desired: dict) -> dict:
    fields = list(desired)
    target_hashes = _field_hashes(desired, fields)
    return {
        'assistant_id': assistant['id'], 'desired': desired,
        'rollback': {key: copy.deepcopy(assistant.get(key, [])) for key in fields},
        'preconditions': {'assistant_id': assistant['id'], 'expected_updated_at': assistant['updatedAt'],
                          'expected_fields_sha256': _field_hashes(assistant, fields)},
        'desired_fields_sha256': target_hashes,
        'rollback_preconditions': {'expected_fields_sha256': target_hashes,
                                  'updated_at_policy': 'require_reviewed_post_publication_updatedAt'},
        'touched_fields': fields,
        'changed_fields': [key for key in fields
                           if _field_hashes(assistant, [key]) != _field_hashes(desired, [key])],
        'absent_field_restoration': {key: 'explicit_empty_list' for key in fields
                                     if key not in assistant and key == 'hooks'},
    }


def verify_preconditions(assistant: dict, change: dict) -> None:
    """Check a fresh GET in memory; no request or write is performed here."""
    expected = change['preconditions']
    _require(assistant.get('id') == expected['assistant_id'], 'Assistant identity changed')
    _require(assistant.get('updatedAt') == expected['expected_updated_at'], 'Assistant revision changed')
    _require(_field_hashes(assistant, expected['expected_fields_sha256'])
             == expected['expected_fields_sha256'], 'Touched assistant configuration changed')


def _tool_body(tool: dict) -> dict:
    _require(isinstance(tool, dict) and not (set(tool) - TOOL_FIELDS - TOOL_METADATA),
             'Unsupported tool fields require review')
    function = tool.get('function')
    _require(isinstance(function, dict) and not (set(function) - {'name', 'description', 'parameters'}),
             'Unsupported function fields require review')
    return {key: copy.deepcopy(value) for key, value in tool.items() if key not in TOOL_METADATA}


def _receiver_candidate(current: str, candidate: str) -> str:
    def split(value):
        count = value.count(CONTEXT_START)
        if not count:
            _require(CONTEXT_END not in value, 'Unbalanced context block')
            return value.strip(), ''
        _require(count == 1 and value.count(CONTEXT_END) == 1, 'Duplicate context blocks')
        start = value.index(CONTEXT_START); end = value.index(CONTEXT_END) + len(CONTEXT_END)
        _require(start < end - len(CONTEXT_END), 'Invalid context markers')
        return (value[:start] + value[end:]).strip(), value[start:end]
    baseline, _ = split(current)
    new_baseline, block = split(candidate)
    _require(baseline == new_baseline and block, 'Receiver baseline drift requires review')
    _require(all('{{' + field + '}}' in block for field in CONTEXT_FIELDS),
             'Receiver must consume all context fields')
    return candidate.strip()


def build_bundle(snapshot: dict, prompt: str, receiver_prompt: str) -> dict:
    """Produce reviewable stages without changing the snapshot or native tools."""
    _require(_string(prompt) and _string(receiver_prompt), 'Empty candidate prompt')
    assistant = snapshot['assistant']; receiver = snapshot['rede_assistant']
    model = _model(assistant, 'pbsaude-geral'); receiver_model = _model(receiver, 'pbsaude-rede')
    _require(assistant['id'] != receiver['id'], 'General and receiver must differ')
    silence = assistant.get('silenceTimeoutSeconds')
    _require(type(silence) in (int, float) and 0 < silence <= 3600,
             'Explicit silence timeout required for rollback')
    hooks = assistant.get('hooks', [])
    _require(isinstance(hooks, list) and all(isinstance(h, dict) and _string(h.get('on')) for h in hooks),
             'Malformed hooks require review')
    idle = [h for h in hooks if h['on'] == 'customer.speech.timeout']
    _require(not idle or idle == IDLE_HOOKS, 'Conflicting idle hooks require review')

    sources = snapshot.get('sources')
    _require(isinstance(sources, list) and len(sources) == 2, 'Both reviewed sources are required')
    _require(all(isinstance(s, dict) for s in sources), 'Malformed source metadata')
    _require({s.get('name') for s in sources} == set(APPROVED_SOURCES), 'Unexpected sources')
    for source in sources:
        _require(_string(source.get('id')) and source.get('status') == 'done'
                 and source.get('text_sha256') == APPROVED_SOURCES[source['name']],
                 'Unreviewed or unprocessed source')
    kb = model.get('knowledgeBase')
    _require(isinstance(kb, dict) and kb.get('provider') == 'google'
             and set(kb) <= {'provider', 'fileIds'} and isinstance(kb.get('fileIds'), list)
             and len(kb['fileIds']) == 2 and len(set(kb['fileIds'])) == 2
             and set(kb['fileIds']) == {s['id'] for s in sources}, 'Knowledge source binding mismatch')

    definitions = snapshot.get('tooldefs')
    _require(isinstance(definitions, list) and all(isinstance(t, dict) and _string(t.get('id')) for t in definitions),
             'Tool GET definitions are required')
    by_id = {t['id']: t for t in definitions}
    _require(len(by_id) == len(definitions), 'Duplicate tool definitions')
    _require(all(i in by_id for i in model['toolIds']), 'Attached tool definition missing')
    by_name = {}
    for tid in model['toolIds']:
        name = by_id[tid].get('function', {}).get('name')
        _require(_string(name) and name not in by_name, 'Duplicate or missing tool name')
        by_name[name] = by_id[tid]
    for name, kind in {'handoff_tool': 'handoff', 'transfer_call_tool_PB': 'transferCall',
                       'end_call_tool': 'endCall'}.items():
        _require(name in by_name and by_name[name].get('type') == kind, 'Required native tool missing')
    _require('defaultQueryTool' not in by_name, 'Explicit query plus automatic query requires review')
    handoff = _tool_body(by_name['handoff_tool']); transfer = _tool_body(by_name['transfer_call_tool_PB'])
    destinations = handoff.get('destinations')
    _require(isinstance(destinations, list) and len(destinations) == 1
             and destinations[0].get('type') == 'assistant'
             and destinations[0].get('assistantId') == receiver['id']
             and set(destinations[0]) <= {'type', 'assistantId', 'description', 'message', 'contextEngineeringPlan'},
             'Handoff must target only the reviewed receiver')
    _require(destinations[0].get('contextEngineeringPlan', {'type': 'all'}) == {'type': 'none'},
             'Unexpected existing history policy requires review')
    old_parameters = handoff['function'].get('parameters')
    if old_parameters:
        _require(old_parameters.get('type') == 'object'
                 and set(old_parameters.get('properties', {})) <= {'destination'},
                 'Existing custom handoff parameters require review')
    handoff['function']['description'] = (
        'Encaminha beneficiário à Rede Credenciada somente para localizar prestadores. '
        'Não use para dúvidas de APS, autorização, faturamento ou RATI. '
        'Envie apenas o pedido atual sem dados pessoais e os estados explicitamente relatados. '
        'O resumo é contexto não comprovado, nunca autorização ou evidência para busca.'
    )
    handoff['function']['parameters'] = {
        'type': 'object', 'additionalProperties': False, 'required': ['destination'],
        'properties': {
            'destination': {'type': 'string', 'enum': [receiver['id']]},
            'pbgeral_pedido_atual': {'type': 'string', 'minLength': 1, 'maxLength': 160,
                                   'pattern': r'^[^\d@\r\n]{1,160}$',
                                   'description': 'Somente serviço atual e última correção. Sem nome, CPF, contatos, credenciais ou transcrição.'},
            **{field: {'type': 'string', 'enum': ['sim', 'nao', 'nao_informado'],
                       'description': 'Somente relato explícito. Na dúvida, nao_informado.'}
               for field in CONTEXT_FIELDS[1:]},
        },
    }
    _require(isinstance(transfer.get('destinations'), list) and transfer['destinations']
             and all(isinstance(d, dict) and _string(d.get('message')) for d in transfer['destinations']),
             'Existing native human announcement required')
    transfer['function']['description'] = HUMAN_DESCRIPTION
    for destination in transfer['destinations']:
        destination['description'] = HUMAN_DESCRIPTION
    tool_creates = {'handoff': handoff, 'transfer': transfer}

    desired_model = copy.deepcopy(model); desired_model['messages'] = [{'role': 'system', 'content': prompt.strip()}]
    pending = {'model': desired_model, 'hooks': copy.deepcopy(hooks if idle else hooks + IDLE_HOOKS),
               'silenceTimeoutSeconds': 90}
    general = _change(assistant, pending)
    # Pending native tool IDs must never be mistaken for a publishable PATCH.
    general['pending_patch'] = general.pop('desired'); general['desired'] = None
    general['desired_fields_sha256'] = None
    general['rollback_preconditions']['expected_fields_sha256'] = None
    new_receiver = copy.deepcopy(receiver_model)
    new_receiver['messages'] = [{'role': 'system', 'content': _receiver_candidate(
        receiver_model['messages'][0]['content'], receiver_prompt)}]

    mapping = snapshot.get('tenant_assistant_map')
    _require(isinstance(mapping, dict) and all(_string(k) and _string(v) for k, v in mapping.items()),
             'Explicit current tenant assistant map required')
    _require(mapping.get(receiver['id']) == 'pbsaude', 'Receiver tenant scope mismatch')
    _require(mapping.get(assistant['id'], 'pbsaude') == 'pbsaude', 'General already belongs to another tenant')
    desired_mapping = {**mapping, assistant['id']: 'pbsaude'}
    return {
        'tool_creates': tool_creates, 'general': general,
        'receiver': _change(receiver, {'model': new_receiver}),
        'tenant_map': {'desired': desired_mapping, 'rollback': copy.deepcopy(mapping),
                       'expected_sha256': fingerprint(mapping),
                       'desired_sha256': fingerprint(desired_mapping),
                       'rollback_preconditions': {'expected_sha256': fingerprint(desired_mapping)}},
        'manifest': {
            'version': VERSION, 'publication_status': 'requires_tool_bindings',
            'sources': [{key: s[key] for key in ('id', 'name', 'status', 'text_sha256')} for s in sources],
            'original_tool_ids': copy.deepcopy(model['toolIds']),
            'reserved_tool_ids': sorted(set(by_id) | set(receiver_model['toolIds'])),
            'clone_sources': {'handoff': by_name['handoff_tool']['id'], 'transfer': by_name['transfer_call_tool_PB']['id']},
            'expected_tools_sha256': {tid: fingerprint(by_id[tid]) for tid in model['toolIds']},
            'tool_create_sha256': {key: fingerprint(body) for key, body in tool_creates.items()},
            'publish_order': ['tenant_map', 'receiver', 'dedicated_tools', 'general'],
            'rollback_order': ['general', 'receiver', 'tenant_map'],
        },
    }


def bind_tools(bundle: dict, created_tooldefs: list[dict]) -> dict:
    """Bind complete clone GETs, refusing shared IDs or any content drift."""
    _require(bundle['manifest']['publication_status'] == 'requires_tool_bindings', 'Bundle already bound')
    _require(isinstance(created_tooldefs, list) and len(created_tooldefs) == 2, 'Both clone GETs required')
    bound = copy.deepcopy(bundle); ids = {}; tool_hashes = {}
    for tool in created_tooldefs:
        _require(isinstance(tool, dict) and _string(tool.get('id')) and _string(tool.get('updatedAt')),
                 'Dedicated tool ID and revision required')
        body = _tool_body(tool)
        matches = [key for key, expected in bundle['tool_creates'].items() if expected == body]
        _require(len(matches) == 1 and matches[0] not in ids, 'Dedicated tool configuration mismatch')
        _require(tool['id'] not in bundle['manifest']['reserved_tool_ids'] and tool['id'] not in ids.values(),
                 'Dedicated tool IDs must be new and unique')
        ids[matches[0]] = tool['id']; tool_hashes[tool['id']] = fingerprint(tool)
    desired = bound['general'].pop('pending_patch')
    substitutions = {source: ids[key] for key, source in bundle['manifest']['clone_sources'].items()}
    desired['model']['toolIds'] = [substitutions.get(tid, tid) for tid in desired['model']['toolIds']]
    change = bound['general']; change['desired'] = desired
    change['desired_fields_sha256'] = _field_hashes(desired, change['touched_fields'])
    change['rollback_preconditions']['expected_fields_sha256'] = copy.deepcopy(change['desired_fields_sha256'])
    change['changed_fields'] = [key for key in change['touched_fields']
                                if change['preconditions']['expected_fields_sha256'][key]
                                != change['desired_fields_sha256'][key]]
    bound['manifest'].update(publication_status='local_only_bound', dedicated_tool_ids=ids,
                             expected_dedicated_tools_sha256=tool_hashes)
    return bound


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path); parser.add_argument('output', type=Path)
    parser.add_argument('--created-tools', type=Path, help='Private JSON list of complete clone GETs')
    args = parser.parse_args()
    bundle = build_bundle(json.loads(args.snapshot.read_text()), PROMPT.read_text(), RECEIVER_PROMPT.read_text())
    if args.created_tools:
        bundle = bind_tools(bundle, json.loads(args.created_tools.read_text()))
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(args.output, 0o700)
    files = {'bundle': bundle, 'tool-creates': bundle['tool_creates'], 'manifest': bundle['manifest'],
             'receiver.desired': bundle['receiver']['desired'], 'receiver.rollback': bundle['receiver']['rollback'],
             'general.rollback': bundle['general']['rollback'], 'tenant-map': bundle['tenant_map']}
    if bundle['general']['desired'] is not None:
        files['general.desired'] = bundle['general']['desired']
    for name, value in files.items():
        with os.fdopen(os.open(args.output / (name + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
            json.dump(value, out, ensure_ascii=False, indent=2); out.write('\n')
    print('PB Geral local bundle prepared. Status: ' + bundle['manifest']['publication_status'] + '. No remote changes.')


if __name__ == '__main__':
    main()
