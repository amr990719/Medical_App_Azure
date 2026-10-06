"""The local `.env` loader used by development settings (README "Environment variables")."""

from pathlib import Path

import pytest

from config.envfile import read_env_file

REPO_ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_empty_values_are_skipped_so_setting_defaults_apply(tmp_path):
    # `.env.example` lists names with empty values; copying it must not turn
    # CURRENT_FISCAL_YEAR into '' (int('') fails) or DEV_AUTH_ENABLED into False.
    target: dict[str, str] = {}
    read_env_file(write(tmp_path, "CURRENT_FISCAL_YEAR=\nDEV_AUTH_ENABLED=   \n"), target)
    assert target == {}


def test_non_empty_values_are_loaded(tmp_path):
    target: dict[str, str] = {}
    path = write(tmp_path, "# comment\nAZURITE_BLOB_PORT=10100\nLOG_LEVEL='DEBUG'\n")
    read_env_file(path, target)
    assert target == {"AZURITE_BLOB_PORT": "10100", "LOG_LEVEL": "DEBUG"}


def test_the_real_environment_wins_over_the_file(tmp_path):
    target = {"AZURITE_BLOB_PORT": "10000"}
    read_env_file(write(tmp_path, "AZURITE_BLOB_PORT=10100\n"), target)
    assert target == {"AZURITE_BLOB_PORT": "10000"}


def test_missing_file_is_a_no_op(tmp_path):
    target: dict[str, str] = {}
    read_env_file(tmp_path / "absent.env", target)
    assert target == {}


@pytest.mark.skipif(not REPO_ENV_EXAMPLE.is_file(), reason="repository root not mounted")
def test_a_verbatim_copy_of_env_example_sets_nothing():
    target: dict[str, str] = {}
    read_env_file(REPO_ENV_EXAMPLE, target)
    assert target == {}
