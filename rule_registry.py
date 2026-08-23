"""Versioned rule registry foundation."""

import copy
import json
from pathlib import Path

REGISTRY_KEYS = {
    "buff": "buffs",
    "mitigation": "mitigations",
    "job": "jobs",
    "encounter": "encounters",
    "alias": "aliases",
}

class RegistryError(ValueError):
    pass

class RuleRegistry:
    def __init__(self, kind, data):
        if kind not in REGISTRY_KEYS:
            raise RegistryError(f"Unknown registry kind: {kind}")

        key = REGISTRY_KEYS[kind]
        if not isinstance(data, dict):
            raise RegistryError("Registry root must be an object")
        if not data.get("version"):
            raise RegistryError("Registry version is required")
        if not isinstance(data.get(key), dict):
            raise RegistryError(f"Registry field must be an object: {key}")

        self.kind = kind
        self.key = key
        self.version = str(data["version"])
        self.patch = data.get("patch")
        self._data = copy.deepcopy(data)

    @classmethod
    def load(cls, kind, path):
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RegistryError(f"Failed to load registry: {source}") from exc
        return cls(kind, data)

    def get(self, identifier, default=None):
        return self._data[self.key].get(str(identifier), default)

    def require(self, identifier):
        value = self.get(identifier)
        if value is None:
            raise RegistryError(
                f"Unknown {self.kind} registry entry: {identifier}"
            )
        return value

    def contains(self, identifier):
        return str(identifier) in self._data[self.key]

    def identifiers(self):
        return tuple(self._data[self.key].keys())

    def as_dict(self):
        return copy.deepcopy(self._data)

def load_registry(kind, path):
    return RuleRegistry.load(kind, path)
