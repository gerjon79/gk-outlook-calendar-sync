"""
Converts the Outlook-only Power Automate flow into an Azure Logic App (Consumption) workflow definition.

- Power Automate "OpenApiConnection" actions become Logic Apps "ApiConnection" actions (method/path/queries/body),
  using the Office 365 Outlook connector paths
- Connection "shared_office365" (calendar 1, destination) becomes $connections['outlookDestination'],
  "shared_office365_1" (calendar 2, source) becomes $connections['outlookSource']
- Every "Setting: ..." InitializeVariable action gets its value from a workflow parameter with the same name as the
  variable (defaulting to the value in the flow), so every sync pair can override settings at deployment time

Usage (from this folder): python convert_flow.py  -> writes workflow.json
"""
import json
import re
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
SOURCE_ZIP = HERE.parent / "Power Automate flows" / "v0.4" / "NG-Outlook-calendar-sync-v0.4.zip"

CONNECTIONS = {"shared_office365": "outlookDestination", "shared_office365_1": "outlookSource"}

# operationId -> (method, path template). Path parameters are written as {name}. Taken from the Office 365 Outlook
# connector's swagger (managedApis/office365).
OPERATIONS = {
    "CalendarGetTables_V2": ("get", "/codeless/v1.0/me/calendars"),
    "GetEventsCalendarViewV3": ("get", "/datasets/calendars/v3/tables/items/calendarview"),
    "CalendarDeleteItem_V2": ("delete", "/codeless/v1.0/me/calendars/{calendar}/events/{event}"),
    "V4CalendarPostItem": ("post", "/datasets/calendars/v4/tables/{table}/items"),
    "V4CalendarPatchItem": ("patch", "/datasets/calendars/v4/tables/{table}/items/{id}"),
}

VARIABLE_TYPES = {"string": "String", "integer": "Int", "boolean": "Bool", "array": "Array", "object": "Object",
                  "float": "Float"}
SECURE_VARIABLES = {"syncHelperApiKey"}


def to_interpolation(value: str) -> str:
    """Turns a parameter value into an expression usable inside a URL path segment."""
    if value.startswith("@{") and value.endswith("}"):
        expression = value[2:-1]
    elif value.startswith("@"):
        expression = value[1:]
    else:
        expression = json.dumps(value).replace('"', "'")
    return f"@{{encodeURIComponent({expression})}}"


def convert_connection_action(action: dict) -> dict:
    inputs = action["inputs"]
    host = inputs["host"]
    method, path = OPERATIONS[host["operationId"]]
    params = dict(inputs.get("parameters", {}))

    for name in re.findall(r"{(\w+)}", path):
        path = path.replace("{" + name + "}", to_interpolation(params.pop(name)))

    body, queries = {}, {}
    for key, value in params.items():
        if key.startswith("item/"):
            body[key.removeprefix("item/")] = value
        else:
            queries[key] = value

    new_inputs = {
        "host": {"connection": {"name": f"@parameters('$connections')['{CONNECTIONS[host['connectionName']]}']"
                                        f"['connectionId']"}},
        "method": method,
        "path": path,
    }
    if queries:
        new_inputs["queries"] = queries
    if body:
        new_inputs["body"] = body

    converted = {k: v for k, v in action.items() if k not in ("inputs", "metadata")}
    converted["type"] = "ApiConnection"
    converted["inputs"] = new_inputs
    return converted


def convert_actions(actions: dict, parameters: dict) -> dict:
    result = {}
    for name, action in actions.items():
        action = {k: v for k, v in action.items() if k != "metadata"}
        if action["type"] == "OpenApiConnection":
            action = convert_connection_action(action)
        elif action["type"] == "InitializeVariable" and name.startswith("Setting:"):
            variable = action["inputs"]["variables"][0]
            parameter = {"type": "SecureString" if variable["name"] in SECURE_VARIABLES
                         else VARIABLE_TYPES[variable["type"].lower()]}
            if variable["name"] not in SECURE_VARIABLES:
                parameter["defaultValue"] = variable.get("value", "" if variable["type"] == "string" else None)
            parameters[variable["name"]] = parameter
            variable["value"] = f"@parameters('{variable['name']}')"

        for key in ("actions",):
            if key in action:
                action[key] = convert_actions(action[key], parameters)
        for branch in ("else", "default"):
            if branch in action and "actions" in action[branch]:
                action[branch]["actions"] = convert_actions(action[branch]["actions"], parameters)
        for case in action.get("cases", {}).values():
            case["actions"] = convert_actions(case.get("actions", {}), parameters)
        result[name] = action
    return result


def main():
    with zipfile.ZipFile(SOURCE_ZIP) as zf:
        definition_path = next(n for n in zf.namelist() if n.endswith("/definition.json"))
        flow = json.loads(zf.read(definition_path))["properties"]["definition"]

    parameters = {"$connections": {"type": "Object", "defaultValue": {}}}
    workflow = {
        "$schema": flow["$schema"],
        "contentVersion": flow.get("contentVersion", "1.0.0.0"),
        "parameters": parameters,
        "triggers": {k: {kk: vv for kk, vv in v.items() if kk != "metadata"} for k, v in flow["triggers"].items()},
        "actions": convert_actions(flow["actions"], parameters),
        "outputs": {},
    }
    # Drop parameters without a usable default (null) so ARM does not reject them
    for p in parameters.values():
        if "defaultValue" in p and p["defaultValue"] is None:
            del p["defaultValue"]

    leftover = re.findall(r"OpenApiConnection|\$authentication|shared_office365", json.dumps(workflow))
    assert not leftover, f"Unconverted references left: {set(leftover)}"

    (HERE / "workflow.json").write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Wrote workflow.json with parameters:", ", ".join(k for k in parameters if k != "$connections"))


if __name__ == "__main__":
    main()
