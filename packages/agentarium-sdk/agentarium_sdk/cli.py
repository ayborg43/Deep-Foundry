from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .manifest import ManifestError, load_manifest, validate_manifest


def _request(base_url: str, token: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1{path}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Agentarium returned HTTP {exc.code}: {detail}") from exc


def _validated(path: str) -> tuple[dict, Path]:
    source = Path(path).resolve()
    return validate_manifest(load_manifest(source)), source.parent


def cmd_validate(args: argparse.Namespace) -> int:
    manifest, root = _validated(args.manifest)
    instructions = manifest.get("instructions_file")
    if instructions and not (root / instructions).is_file():
        raise ManifestError(f"instructions_file does not exist: {instructions}")
    print(f"Valid {manifest['listing_type']}: {manifest['name']}@{manifest['version']}")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    manifest, root = _validated(args.manifest)
    instructions = manifest.get("instructions_file")
    if instructions:
        content = (root / instructions).read_text(encoding="utf-8")
        if len(content.strip()) < 40:
            raise ManifestError("Skill instructions must contain at least 40 characters.")
    print(f"Manifest and local contract tests passed for {manifest['name']}.")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    manifest, root = _validated(args.manifest)
    token = args.token or os.getenv("AGENTARIUM_TOKEN")
    if not token:
        raise ManifestError("Pass --token or set AGENTARIUM_TOKEN.")
    listing = _request(args.base_url, token, "/marketplace/listings", {
        "publisher_workspace_id": args.workspace_id,
        "listing_type": manifest["listing_type"], "name": manifest["name"],
        "summary": manifest["summary"], "visibility": manifest.get("visibility", "public"),
        "pricing_model": manifest.get("pricing_model", "free"),
    })
    content = ""
    if manifest.get("instructions_file"):
        content = (root / manifest["instructions_file"]).read_text(encoding="utf-8")
    version = _request(args.base_url, token, f"/marketplace/listings/{listing['id']}/versions", {
        "version_string": manifest["version"], "manifest": manifest,
        "changelog": args.changelog, "instruction_content": content,
    })
    print(json.dumps({"listing_id": listing["id"], **version}, indent=2, default=str))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentarium")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("validate", cmd_validate), ("test", cmd_test)):
        command = commands.add_parser(name); command.add_argument("manifest"); command.set_defaults(handler=handler)
    publish = commands.add_parser("publish"); publish.add_argument("manifest"); publish.add_argument("--workspace-id", required=True)
    publish.add_argument("--base-url", default=os.getenv("AGENTARIUM_URL", "http://localhost:8000")); publish.add_argument("--token"); publish.add_argument("--changelog", default="Published with Agentarium SDK"); publish.set_defaults(handler=cmd_publish)
    args = parser.parse_args()
    try:
        raise SystemExit(args.handler(args))
    except (ManifestError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr); raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
