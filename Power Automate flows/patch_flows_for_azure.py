"""
Creates the v0.4 flow packages from the v0.3 ones, adapted to the self-hosted sync helper service on Azure:
- the "calendar sync helper server URL" setting points to the Azure Container App
- a new setting "Setting: sync helper API key" (variable syncHelperApiKey) is added right after the URL setting
- every HTTP action that calls the sync helper service sends the X-API-Key header

Usage (from this folder): python patch_flows_for_azure.py
"""
import json
import zipfile
from pathlib import Path

SOURCE_VERSION = "v0.3"
TARGET_VERSION = "v0.4"
SERVER_URL = "https://outlook-sync.braveisland-42f2d157.westeurope.azurecontainerapps.io/v1"
API_KEY_PLACEHOLDER = "PASTE-YOUR-API-KEY-HERE"

URL_SETTING = "Setting:_calendar_sync_helper_server_URL"
API_KEY_SETTING = "Setting:_sync_helper_API_key"

HERE = Path(__file__).parent


def iter_actions(actions: dict):
    """Yields (name, action) for all actions, including those nested in scopes, conditions and switches."""
    for name, action in actions.items():
        yield name, action
        yield from iter_actions(action.get("actions", {}))
        yield from iter_actions(action.get("else", {}).get("actions", {}))
        for case in action.get("cases", {}).values():
            yield from iter_actions(case.get("actions", {}))
        yield from iter_actions(action.get("default", {}).get("actions", {}))


def patch_definition(definition: dict) -> list[str]:
    props = definition["properties"]
    props["displayName"] = props["displayName"].replace(SOURCE_VERSION, TARGET_VERSION)
    actions = props["definition"]["actions"]

    # 1. Server URL
    actions[URL_SETTING]["inputs"]["variables"][0]["value"] = SERVER_URL

    # 2. New API key setting, chained directly after the URL setting
    if API_KEY_SETTING not in actions:
        for action in actions.values():
            run_after = action.get("runAfter", {})
            if URL_SETTING in run_after:
                run_after[API_KEY_SETTING] = run_after.pop(URL_SETTING)
        actions[API_KEY_SETTING] = {
            "runAfter": {URL_SETTING: ["Succeeded"]},
            "type": "InitializeVariable",
            "inputs": {"variables": [{"name": "syncHelperApiKey", "type": "string", "value": API_KEY_PLACEHOLDER}]},
            "description": "API key of the sync helper service (sent as X-API-Key header). "
                           "Get it from the Azure portal: Container App outlook-sync > Secrets > api-key",
        }

    # 3. X-API-Key header on every HTTP action that calls the sync helper service
    patched = []
    for name, action in iter_actions(actions):
        if action.get("type") == "Http" and "syncHelperServerUrl" in action["inputs"].get("uri", ""):
            action["inputs"].setdefault("headers", {})["X-API-Key"] = "@{variables('syncHelperApiKey')}"
            patched.append(name)
    return patched


def patch_zip(source: Path, target: Path):
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith("/definition.json"):
                definition = json.loads(data)
                patched = patch_definition(definition)
                data = json.dumps(definition, ensure_ascii=False).encode("utf-8")
                print(f"{target.name}: added X-API-Key to {patched}")
            elif info.filename == "manifest.json":
                data = data.decode("utf-8").replace(SOURCE_VERSION, TARGET_VERSION).encode("utf-8")
            dst.writestr(info, data)


def main():
    target_dir = HERE / TARGET_VERSION
    target_dir.mkdir(exist_ok=True)
    for source in sorted((HERE / SOURCE_VERSION).glob("*.zip")):
        target = target_dir / source.name.replace(SOURCE_VERSION, TARGET_VERSION)
        patch_zip(source, target)

    # Keep latest-source (pretty-printed Outlook <-> Google flow) in sync
    with zipfile.ZipFile(target_dir / f"NG-Outlook-Google-calendar-sync-{TARGET_VERSION}.zip") as zf:
        for name in zf.namelist():
            if name.endswith("/definition.json") or name == "manifest.json":
                content = json.loads(zf.read(name))
                out = HERE / "latest-source" / Path(name).name
                out.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
