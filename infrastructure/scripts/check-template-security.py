#!/usr/bin/env python3
"""Security guard for the compiled ARM template of main.bicep (PROMPT.md §33, §34, §47).

    az bicep build --file infrastructure/main.bicep --outfile main.json
    python infrastructure/scripts/check-template-security.py main.json
    python infrastructure/scripts/check-template-security.py main.json --self-test

Walks every nested module and fails when a security property that must be a literal in the
template is missing or different: private blob container, no shared keys or anonymous access,
TLS 1.2, Key Vault RBAC + purge protection, Entra-only PostgreSQL by default with TLS enforced,
no registry admin user, no Azure OpenAI keys, HTTPS-only ingress, no secret in the outputs.
`--self-test` breaks each rule in memory and checks that the guard notices. Standard library only.
"""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Iterator

# (resource type, dotted path under "properties", required literal value)
RESOURCE_RULES: list[tuple[str, str, object]] = [
    ("Microsoft.Storage/storageAccounts", "allowBlobPublicAccess", False),
    ("Microsoft.Storage/storageAccounts", "allowSharedKeyAccess", False),
    ("Microsoft.Storage/storageAccounts", "defaultToOAuthAuthentication", True),
    ("Microsoft.Storage/storageAccounts", "allowCrossTenantReplication", False),
    ("Microsoft.Storage/storageAccounts", "minimumTlsVersion", "TLS1_2"),
    ("Microsoft.Storage/storageAccounts", "supportsHttpsTrafficOnly", True),
    ("Microsoft.Storage/storageAccounts/blobServices/containers", "publicAccess", "None"),
    ("Microsoft.KeyVault/vaults", "enableRbacAuthorization", True),
    ("Microsoft.KeyVault/vaults", "enableSoftDelete", True),
    ("Microsoft.KeyVault/vaults", "enablePurgeProtection", True),
    ("Microsoft.DBforPostgreSQL/flexibleServers", "authConfig.activeDirectoryAuth", "Enabled"),
    ("Microsoft.ContainerRegistry/registries", "adminUserEnabled", False),
    ("Microsoft.ContainerRegistry/registries", "anonymousPullEnabled", False),
    ("Microsoft.CognitiveServices/accounts", "disableLocalAuth", True),
    ("Microsoft.App/containerApps", "configuration.ingress.allowInsecure", False),
]

# PostgreSQL server parameters (flexibleServers/configurations): name -> required value.
POSTGRES_CONFIGURATIONS = {"require_secure_transport": "on", "ssl_min_protocol_version": "TLSv1.2"}

# main.bicep parameters whose default must stay on the safe side.
PARAMETER_DEFAULTS = {"postgresPasswordAuth": False, "enableOcr": False}

SECRET_WORDS = ("secret", "password", "connectionstring", "token", "sas")


def resources(template: dict) -> Iterator[dict]:
    """Every resource of the template and of its nested deployments (Bicep modules)."""
    items = template.get("resources", [])
    for resource in items.values() if isinstance(items, dict) else items:
        if resource.get("type") == "Microsoft.Resources/deployments":
            yield from resources(resource["properties"]["template"])
        else:
            yield resource


def lookup(properties: dict, path: str) -> object:
    value: object = properties
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return KeyError(path)
        value = value[part]
    return value


def check(template: dict) -> list[str]:
    problems: list[str] = []
    found = {resource_type for resource_type, _, _ in RESOURCE_RULES}
    seen: set[str] = set()
    configurations: dict[str, object] = {}

    for resource in resources(template):
        resource_type = resource.get("type", "")
        seen.add(resource_type)
        if resource_type == "Microsoft.DBforPostgreSQL/flexibleServers/configurations":
            name = str(resource.get("name", ""))
            for setting in POSTGRES_CONFIGURATIONS:
                if f"'{setting}'" in name:
                    configurations[setting] = resource.get("properties", {}).get("value")
        for rule_type, path, expected in RESOURCE_RULES:
            if resource_type != rule_type:
                continue
            actual = lookup(resource.get("properties", {}), path)
            if actual != expected:
                problems.append(f"{resource_type}: {path} must be {expected!r}, found {actual!r}")

    for missing in sorted(found - seen):
        problems.append(f"{missing}: resource not found (the guard would check nothing)")
    for setting, expected in POSTGRES_CONFIGURATIONS.items():
        if configurations.get(setting) != expected:
            problems.append(
                f"PostgreSQL {setting} must be {expected!r}, found {configurations.get(setting)!r}"
            )

    parameters = template.get("parameters", {})
    for name, expected in PARAMETER_DEFAULTS.items():
        actual = parameters.get(name, {}).get("defaultValue", KeyError(name))
        if actual != expected:
            problems.append(f"parameter {name}: default must be {expected!r}, found {actual!r}")
    for name, parameter in parameters.items():
        if parameter.get("type", "").lower() == "securestring" and parameter.get("defaultValue"):
            problems.append(f"parameter {name}: a secure parameter must not have a default value")

    for name, output in template.get("outputs", {}).items():
        lowered = name.lower()
        if (
            output.get("type", "").lower() in {"securestring", "secureobject"}
            or any(word in lowered for word in SECRET_WORDS)
            or lowered.endswith(("key", "keys"))
        ):
            problems.append(f"output {name}: outputs are stored in the deployment history")
    return problems


def self_test(template: dict) -> list[str]:
    """Break every rule once; each mutation must be reported."""
    failures: list[str] = []
    if check(template):
        return ["the unmodified template must pass before the self-test"]

    def mutated(predicate, mutate) -> dict:
        broken = copy.deepcopy(template)
        for resource in resources(broken):
            if predicate(resource):
                mutate(resource)
        return broken

    for rule_type, path, expected in RESOURCE_RULES:

        def flip(resource, path=path, expected=expected):
            node = resource["properties"]
            *parents, leaf = path.split(".")
            for part in parents:
                node = node[part]
            node[leaf] = (not expected) if isinstance(expected, bool) else "Disabled-by-mutation"

        broken = mutated(lambda r, t=rule_type: r.get("type") == t, flip)
        if not check(broken):
            failures.append(f"not caught: {rule_type} {path}")

    for setting in POSTGRES_CONFIGURATIONS:
        broken = mutated(
            lambda r, s=setting: f"'{s}'" in str(r.get("name", "")),
            lambda r: r["properties"].__setitem__("value", "off"),
        )
        if not check(broken):
            failures.append(f"not caught: PostgreSQL {setting}")

    for name, expected in PARAMETER_DEFAULTS.items():
        broken = copy.deepcopy(template)
        broken["parameters"][name]["defaultValue"] = not expected
        if not check(broken):
            failures.append(f"not caught: parameter default {name}")

    broken = copy.deepcopy(template)
    broken["outputs"]["storageAccountKey"] = {"type": "string", "value": "[listKeys()]"}
    if not check(broken):
        failures.append("not caught: secret-looking output")
    return failures


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        template = json.load(handle)
    if "--self-test" in argv[2:]:
        failures = self_test(template)
        for failure in failures:
            print(f"SELF-TEST FAILED: {failure}")
        rules = len(RESOURCE_RULES) + len(POSTGRES_CONFIGURATIONS) + len(PARAMETER_DEFAULTS) + 1
        print(f"self-test: {rules - len(failures)}/{rules} broken rules caught")
        return 1 if failures else 0
    problems = check(template)
    for problem in problems:
        print(f"INSECURE: {problem}")
    print(f"template security: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
