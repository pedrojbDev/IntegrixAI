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


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def build_bundle(snapshot: dict, prompt: str) -> dict:
    assistant = snapshot["assistant"]
    model = assistant["model"]
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
    return {
        "desired": {"model": desired_model},
        "rollback": {"model": copy.deepcopy(model)},
        "manifest": {
            "version": "pbsaude-flow-v16-candidate",
            "assistant_id": assistant["id"],
            "expected_updated_at": assistant.get("updatedAt"),
            "expected_model_sha256": fingerprint(model),
            "desired_model_sha256": fingerprint(desired_model),
            "prompt_sha256": hashlib.sha256(prompt.strip().encode()).hexdigest(),
            "changed_fields": ["model.messages", "model.toolIds"],
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
