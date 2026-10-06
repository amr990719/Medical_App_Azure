"""Load the repository-root `.env` for development settings.

django-environ's `read_env` copies every line, including `KEY=` with an empty value. `.env.example`
lists names with empty values, so a verbatim copy would replace each setting's default with ''
(`int('')` fails, booleans turn False). Empty values are therefore skipped, and the real
environment always wins over the file.
"""

import os
from collections.abc import MutableMapping
from pathlib import Path

import environ


def read_env_file(path: Path, target: MutableMapping[str, str] = os.environ) -> None:
    if not path.is_file():
        return
    collector = type("_EnvFile", (environ.Env,), {"ENVIRON": {}})
    collector.read_env(path)  # parses quotes and comments into collector.ENVIRON only
    for key, value in collector.ENVIRON.items():
        if value.strip():
            target.setdefault(key, value)
