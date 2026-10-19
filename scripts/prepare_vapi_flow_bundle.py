"""Build reviewable local assistant patches. This script has no network client.

Input: a private JSON object with `assistant` and `tooldefs` from Vapi GETs.
Output: desired/rollback patches and a manifest. Never copy the snapshot into git.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1] / "app/tenants/pbsaude/vapi/prompt.md"
REQUIRED_TOOLS = {
    "search_providers": "function",
    "transfer_call_tool_PB": "transferCall",
    "end_call_tool": "endCall",
}
VERSION = "pbsaude-flow-v18-mitigation"
IDLE_HOOKS = [
    {
        "on": "customer.speech.timeout",
        "options": {"timeoutSeconds": seconds, "triggerMaxCount": 1,
                    "triggerResetMode": "onUserSpeech"},
        "do": [{"type": "say", "exact": message}],
    }
    for seconds, message in (
        (15, "Você ainda está na linha?"),
        (45, "Estou aguardando sua resposta para continuar."),
    )
]


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def build_bundle(snapshot: dict, prompt: str) -> dict:
    assistant = snapshot["assistant"]
    model = assistant["model"]
    if not isinstance(assistant.get("updatedAt"), str) or not assistant["updatedAt"].strip():
        raise ValueError("Snapshot must contain updatedAt for publication preconditions")
    silence = assistant.get("silenceTimeoutSeconds")
    if type(silence) not in (int, float) or not 0 < silence <= 3600:
        raise ValueError("Explicit silenceTimeoutSeconds required for a reviewable rollback; do not guess defaults")
    hooks = assistant.get("hooks", [])
    if not isinstance(hooks, list) or any(
        not isinstance(hook, dict) or not isinstance(hook.get("on"), str)
        for hook in hooks
    ):
        raise ValueError("Review unsupported hooks before preparing a bundle")
    timeout_hooks = [hook for hook in hooks if hook["on"] == "customer.speech.timeout"]
    if timeout_hooks and timeout_hooks != IDLE_HOOKS:
        raise ValueError("Existing silence hooks conflict with the mitigation; review manually")
    # Retain the complete model object: PATCH implementations may replace it.
    # Refuse custom model credentials/URLs instead of copying secrets to a bundle.
    allowed = {"provider", "model", "messages", "toolIds", "tools", "temperature",
               "maxTokens", "numFastTurns", "emotionRecognitionEnabled"}
    if set(model) - allowed:
        raise ValueError("Review unsupported model fields before preparing a bundle")
    if model.get("tools"):
        raise ValueError("Inline tools require manual review; use the attached toolIds snapshot")
    if not isinstance(model.get("messages"), list) or not isinstance(model.get("toolIds"), list):
        raise ValueError("Snapshot must contain model.messages and model.toolIds")
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")
    definitions = {tool["id"]: tool for tool in snapshot["tooldefs"]}
    attached = []
    names = {}
    for tool_id in model["toolIds"]:
        if tool_id not in definitions:
            raise ValueError("Snapshot is missing an attached tool definition")
        tool = definitions[tool_id]
        name = tool.get("function", {}).get("name")
        if name in names:
            raise ValueError("Duplicate tool name in assistant")
        names[name] = tool
        if name != "handoff_human":
            attached.append(tool_id)
    for name, kind in REQUIRED_TOOLS.items():
        if name not in names or names[name].get("type") != kind:
            raise ValueError(f"Missing required tool: {name}")
    transfer = names["transfer_call_tool_PB"]
    destinations = transfer.get("destinations") or []
    if not destinations or not all(d.get("message") for d in destinations):
        raise ValueError("Native transfer announcement must already be configured")
    desired_model = copy.deepcopy(model)
    desired_model["messages"] = [{"role": "system", "content": prompt.strip()}]
    desired_model["toolIds"] = attached
    desired_hooks = copy.deepcopy(hooks if timeout_hooks else hooks + IDLE_HOOKS)
    desired = {"model": desired_model, "hooks": desired_hooks, "silenceTimeoutSeconds": 90}
    # PATCH omission cannot remove a field introduced by the desired patch.
    # Absent hooks have the same behavior as []; never guess numeric defaults.
    rollback = {"model": copy.deepcopy(model), "hooks": copy.deepcopy(hooks),
                "silenceTimeoutSeconds": silence}
    expected_hashes = {
        field: fingerprint({"present": True, "value": assistant[field]}
                           if field in assistant else {"present": False})
        for field in desired
    }
    desired_hashes = {field: fingerprint({"present": True, "value": value})
                      for field, value in desired.items()}
    changed_fields = [f"model.{field}" for field in ("messages", "toolIds")
                      if model[field] != desired_model[field]]
    changed_fields.extend(field for field in ("hooks", "silenceTimeoutSeconds")
                          if expected_hashes[field] != desired_hashes[field])
    return {
        "desired": desired,
        "rollback": rollback,
        "manifest": {
            "version": VERSION,
            "assistant_id": assistant["id"],
            "expected_updated_at": assistant.get("updatedAt"),
            "expected_model_sha256": fingerprint(model),
            "desired_model_sha256": fingerprint(desired_model),
            "expected_fields_sha256": expected_hashes,
            "desired_fields_sha256": desired_hashes,
            "rollback_preconditions": {
                "expected_fields_sha256": copy.deepcopy(desired_hashes),
                "updated_at_policy": "require_reviewed_post_publication_updatedAt",
            },
            "absent_field_restoration": {} if "hooks" in assistant else {"hooks": "explicit_empty_list"},
            "prompt_sha256": hashlib.sha256(prompt.strip().encode()).hexdigest(),
            "touched_fields": list(desired),
            "changed_fields": changed_fields,
            "removed_tools": ["handoff_human"] if "handoff_human" in names else [],
            "native_tool_edits": [],
            "publication_status": "local_only",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    bundle = build_bundle(json.loads(args.snapshot.read_text()), PROMPT.read_text())
    # Never overwrite an existing bundle. Snapshots and output remain private.
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in bundle.items():
        path = args.output / f"{name}.json"
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
            json.dump(content, out, ensure_ascii=False, indent=2)
            out.write("\n")
    print(f"Local bundle prepared: {args.output}. No remote changes made.")


if __name__ == "__main__":
    main()
