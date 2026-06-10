"""
Godot MCP Server - Skill Utilities
Utility functions for handling skill files and paths.
"""

from pathlib import Path
import re

# Skill directory (repo root /skills)
SKILLS_DIR = Path("skills").resolve()
GUIDELINE_FILE_NAME = "skill_creation_guideline.txt"


def get_skills_dir() -> Path:
    """Return the absolute skill directory path."""
    return SKILLS_DIR


def ensure_skills_dir() -> Path:
    """Ensure the skill directory exists and return it."""
    skills_dir = get_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def is_within_directory(base_dir: Path, target_path: Path) -> bool:
    """Return True when target_path is located inside base_dir."""
    base = base_dir.resolve(strict=False)
    target = target_path.resolve(strict=False)
    return target.is_relative_to(base)


def relative_skill_path(path: Path) -> str:
    """Render a skill path relative to /skills when possible."""
    resolved = path.resolve(strict=False)
    skills_dir = get_skills_dir().resolve(strict=False)
    if resolved.is_relative_to(skills_dir):
        return resolved.relative_to(skills_dir).as_posix()
    return resolved.as_posix()


def validate_skill_path(relative_path: str) -> Path:
    """
    Validate that the requested path stays inside the skills directory.

    Raises:
        ValueError: If the path escapes the skills directory.
        FileNotFoundError: If the file does not exist.
    """
    skills_dir = get_skills_dir()
    requested_path = (skills_dir / relative_path).resolve(strict=False)
    if not is_within_directory(skills_dir, requested_path):
        raise ValueError("Access denied: Path outside allowed skills directory")
    if not requested_path.exists():
        raise FileNotFoundError(f"Skill file not found: {relative_path}")
    return requested_path


def sanitize_skill_name(name: str) -> str:
    """
    Convert a user-provided skill title into a safe filename stem.

    The result is lower-case, hyphen-separated, and safe for plain text files.
    """
    cleaned = name.strip().lower().replace("/", "-").replace("\\", "-")
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "skill"


def build_skill_filename(title: str) -> str:
    """Build a `.txt` filename for a new skill."""
    return f"{sanitize_skill_name(title)}.txt"


def build_skill_path(title: str) -> Path:
    """Build an absolute path for a new skill file."""
    return ensure_skills_dir() / build_skill_filename(title)


def infer_skill_tags_from_path(path: Path) -> list[str]:
    """
    Infer skill tags from the file path when the skill file omits explicit tags.

    Prefer directory segments first, then split the filename stem into tokens.
    """
    relative = Path(path.name)
    try:
        relative = path.resolve(strict=False).relative_to(get_skills_dir().resolve(strict=False))
    except ValueError:
        pass

    tags: list[str] = []
    for part in relative.parts[:-1]:
        part = part.strip().lower()
        if part:
            tags.append(part)

    stem_tokens = [
        token
        for token in re.split(r"[-_\s]+", Path(relative.name).stem.lower())
        if token
    ]
    if not tags:
        tags.extend(stem_tokens)
    else:
        for token in stem_tokens:
            if token not in tags:
                tags.append(token)
    return tags or [sanitize_skill_name(Path(relative.name).stem)]
