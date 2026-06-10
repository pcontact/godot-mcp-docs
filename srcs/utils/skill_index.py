"""
Godot MCP Server - Skill Index
Metadata parsing and cached indexing for skill files in /skills.
"""

from dataclasses import dataclass
import logging
import re
from pathlib import Path

from srcs.utils.skill_utils import (
    GUIDELINE_FILE_NAME,
    get_skills_dir,
    infer_skill_tags_from_path,
    relative_skill_path,
)

logger = logging.getLogger(__name__)

TITLE_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)
SECTION_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "use",
    "with",
    "when",
    "while",
}


@dataclass(frozen=True)
class SkillRecord:
    title: str
    summary: str
    tags: tuple[str, ...]
    path: str
    content: str

    @property
    def search_text(self) -> str:
        return " ".join(
            [
                self.title,
                self.summary,
                " ".join(self.tags),
                self.path,
                self.content,
            ]
        ).lower()


def _tokenize(value: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(value.lower()) if token and token not in STOPWORDS]


def _paragraph_from_text(text: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    return paragraphs[0] if paragraphs else ""


def _extract_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in text.splitlines():
        header_match = SECTION_PATTERN.match(line.strip())
        if header_match:
            current_section = header_match.group(1).strip().lower()
            sections.setdefault(current_section, [])
            continue
        if current_section is not None:
            sections.setdefault(current_section, []).append(line)

    return {section: "\n".join(lines).strip() for section, lines in sections.items()}


def _extract_title(text: str, path: Path) -> str:
    match = TITLE_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def _extract_summary(text: str, sections: dict[str, str]) -> str:
    for section_name in ("summary", "purpose"):
        section_text = sections.get(section_name, "").strip()
        if section_text:
            paragraph = _paragraph_from_text(section_text)
            if paragraph:
                return paragraph

    fallback = _paragraph_from_text(text)
    if fallback:
        return fallback

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines[:2]) if lines else ""


def _extract_tags(text: str, path: Path, sections: dict[str, str]) -> list[str]:
    tag_block = sections.get("tags", "").strip()
    if tag_block:
        tags: list[str] = []
        for raw_tag in re.split(r"[,\n;/]+", tag_block):
            tag = raw_tag.strip().lower()
            if tag and tag not in tags:
                tags.append(tag)
        if tags:
            return tags
    return infer_skill_tags_from_path(path)


def parse_skill_file(path: Path) -> dict:
    """
    Parse a skill file into the v2 metadata structure.

    Returns:
        {
            "title": str,
            "summary": str,
            "tags": list[str],
            "path": str,
            "content": str,
        }
    """
    content = path.read_text(encoding="utf-8")
    return parse_skill_text(content, path)


def parse_skill_text(content: str, path: Path) -> dict:
    """
    Parse skill text into the v2 metadata structure.

    Returns:
        {
            "title": str,
            "summary": str,
            "tags": list[str],
            "path": str,
            "content": str,
        }
    """
    sections = _extract_sections(content)
    return {
        "title": _extract_title(content, path),
        "summary": _extract_summary(content, sections),
        "tags": _extract_tags(content, path, sections),
        "path": relative_skill_path(path),
        "content": content,
    }


def _score_skill(query_tokens: list[str], query_text: str, record: SkillRecord) -> int:
    if not query_tokens and not query_text:
        return 0

    title_tokens = set(_tokenize(record.title))
    summary_tokens = set(_tokenize(record.summary))
    content_tokens = set(_tokenize(record.content))
    path_tokens = set(_tokenize(record.path.replace("/", " ")))
    tag_tokens = set()
    for tag in record.tags:
        tag_tokens.update(_tokenize(tag))

    score = 0
    for token in query_tokens:
        if token in tag_tokens:
            score += 3
        if token in title_tokens or token in path_tokens:
            score += 2
        if token in summary_tokens:
            score += 2
        if token in content_tokens:
            score += 1

    if query_text and query_text in record.title.lower():
        score += 3
    if query_text and query_text in record.summary.lower():
        score += 2
    if query_text and query_text in record.content.lower():
        score += 1

    return score


class SkillIndex:
    """Cached index over /skills skill files."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        self.skills_dir = skills_dir or get_skills_dir()
        self._records: list[SkillRecord] = []
        self._signature: tuple[tuple[str, int, int], ...] = ()

    def _skill_files(self) -> list[Path]:
        if not self.skills_dir.exists():
            return []
        files = [
            path
            for path in self.skills_dir.rglob("*.txt")
            if path.is_file() and path.name != GUIDELINE_FILE_NAME
        ]
        return sorted(files, key=lambda item: item.relative_to(self.skills_dir).as_posix())

    def _current_signature(self) -> tuple[tuple[str, int, int], ...]:
        signature: list[tuple[str, int, int]] = []
        for path in self._skill_files():
            stat = path.stat()
            signature.append((path.relative_to(self.skills_dir).as_posix(), stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def refresh(self) -> "SkillIndex":
        """Rescan and parse all skill files into the cache."""
        self._records = []
        for path in self._skill_files():
            try:
                parsed = parse_skill_file(path)
            except Exception as exc:  # pragma: no cover - logged, not fatal
                logger.warning("Skipping unreadable skill file %s: %s", path, exc)
                continue
            self._records.append(
                SkillRecord(
                    title=parsed["title"],
                    summary=parsed["summary"],
                    tags=tuple(parsed["tags"]),
                    path=parsed["path"],
                    content=parsed["content"],
                )
            )
        self._signature = self._current_signature()
        return self

    def all_skills(self) -> list[SkillRecord]:
        """Return the cached skill records, refreshing only when the tree changes."""
        if self._signature != self._current_signature():
            self.refresh()
        return list(self._records)

    def search(self, query: str, limit: int = 5) -> list[tuple[int, SkillRecord]]:
        """Return scored skill records for a query."""
        query_text = query.lower().strip()
        query_tokens = _tokenize(query_text)
        scored = [
            (_score_skill(query_tokens, query_text, record), record)
            for record in self.all_skills()
        ]
        scored.sort(key=lambda item: (item[0], item[1].title.lower(), item[1].path), reverse=True)
        if limit > 0:
            return scored[:limit]
        return scored


SKILL_INDEX = SkillIndex()
