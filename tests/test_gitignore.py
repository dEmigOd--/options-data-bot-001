"""Test that .gitignore includes .env so credentials are not committed."""

from pathlib import Path


def _gitignore_entries() -> list:
    """Parse .gitignore: return list of non-empty, non-comment patterns (stripped)."""
    root = Path(__file__).resolve().parents[1]
    path = root / ".gitignore"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            entries.append(s)
    return entries


def test_env_or_dotenv_is_ignored() -> None:
    """Ensure .env or env/.env is in .gitignore so credentials are never committed."""
    entries = _gitignore_entries()
    has_dotenv = ".env" in entries
    has_env_dotenv = "env/.env" in entries
    assert has_dotenv or has_env_dotenv, (
        ".gitignore must contain .env or env/.env to avoid committing credentials; found neither"
    )
