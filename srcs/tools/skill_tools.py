"""
Godot MCP Server - Skill Tools

Retrieval-first tools for discovering, reading, creating, updating, and
evaluating skills stored in the /skills folder.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from srcs.server import mcp
from srcs.utils.docs_utils import get_docs_dir
from srcs.utils.file_utils import read_cached_file
from srcs.utils.skill_index import SKILL_INDEX, SkillRecord, parse_skill_text
from srcs.utils.skill_utils import (
    build_skill_path,
    ensure_skills_dir,
    get_skills_dir,
    sanitize_skill_name,
    validate_skill_path,
)

logger = logging.getLogger(__name__)

DEPRECATION_BANNER = "⚠️ Deprecated. Use search_skills(query) instead."
UPDATE_MODES = {"replace", "append"}
SKILL_MATCH_THRESHOLD = 5
SEARCH_RESULTS_LIMIT = 5

API_STOPWORDS = {
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

API_TAG_HINTS = {
    "movement": {"movement", "move", "movement3d", "movement2d", "chase", "follow", "climb", "grapple", "grappling", "jump", "traverse", "traversal"},
    "navigation": {"navigation", "path", "pathfinding", "nav", "route", "agent"},
    "ai": {"ai", "enemy", "npc", "behavior", "decision", "state", "planning"},
    "physics": {"physics", "collision", "rigidbody", "force", "velocity", "impulse"},
    "animation": {"animation", "anim", "blend", "pose", "rotate"},
    "3d": {"3d", "three", "dimension", "dimensions"},
    "2d": {"2d", "two", "dimension", "dimensions"},
}


def _tokenize(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return [token for token in tokens if token and token not in API_STOPWORDS]


def _render_skill_record(record: SkillRecord) -> str:
    return (
        f"Title: {record.title}\n"
        f"Summary: {record.summary or 'No summary available.'}\n"
        f"Tags: {', '.join(record.tags) if record.tags else 'none'}\n"
        f"Path: {record.path}\n\n"
        f"Content:\n{record.content}"
    )


def _format_search_results(query: str, results: list[tuple[int, SkillRecord]]) -> str:
    if not results:
        return (
            f"No indexed skills found for: \"{query}\".\n"
            "Use create_skill() to add one, or discover_missing_skill(task) to propose a new skill."
        )

    top_score = results[0][0]
    if top_score <= 0:
        return (
            f"No strong skill matches found for: \"{query}\".\n"
            "Use discover_missing_skill(task) to propose a new skill, or search again with a more specific query."
        )

    lines = [f'Top matching skills for: "{query}"', ""]
    for index, (score, record) in enumerate(results, start=1):
        lines.append(f"{index}. {record.path} (score: {score})")
        lines.append(f"   Title: {record.title}")
        lines.append(f"   Summary: {record.summary or 'No summary available.'}")
        lines.append(f"   Tags: {', '.join(record.tags) if record.tags else 'none'}")
        lines.append("")
    lines.append("Read a match with read_skill(path).")
    return "\n".join(lines).rstrip()


def _format_skill_listing(results: list[SkillRecord]) -> str:
    if not results:
        return (
            f"{DEPRECATION_BANNER}\n"
            "No indexed skills found yet."
        )

    lines = [DEPRECATION_BANNER, "", "Indexed skills:"]
    for record in results:
        lines.append(f"- {record.path} :: {record.title}")
    lines.append("")
    lines.append("Use search_skills(query) to rank relevant skills.")
    return "\n".join(lines)


def _load_skill_record(skill_path: str) -> SkillRecord:
    skill_file = validate_skill_path(skill_path)
    parsed = parse_skill_text(read_cached_file(skill_file), skill_file)
    return SkillRecord(
        title=parsed["title"],
        summary=parsed["summary"],
        tags=tuple(parsed["tags"]),
        path=parsed["path"],
        content=parsed["content"],
    )


def _clear_file_cache() -> None:
    read_cached_file.cache_clear()


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        clean = tag.strip().lower()
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized


def _render_skill_body(title: str, summary: str, tags: list[str], content: str) -> str:
    sections = [
        f"# {title}",
        "",
        "## Summary",
        summary.strip() or "Describe the goal of this skill.",
        "",
        "## Tags",
        ", ".join(tags) if tags else "general",
        "",
        "## When to use",
        "Describe the situation where the agent should reach for this skill.",
        "",
        "## Prerequisites",
        "List any required context, systems, or knowledge.",
        "",
        "## Procedure",
        content.strip() or "Describe the step-by-step procedure here.",
        "",
        "## Common mistakes",
        "- Add the mistakes an agent should avoid.",
        "",
        "## Example",
        "- Add a compact example or usage pattern.",
        "",
        "## Notes",
        "- Add extra implementation notes, caveats, or follow-up ideas.",
    ]
    return "\n".join(sections).rstrip() + "\n"


def _infer_tags_for_task(task: str, search_results: list[tuple[int, SkillRecord]]) -> list[str]:
    query_tokens = set(_tokenize(task))
    inferred: list[str] = []

    for tag, hints in API_TAG_HINTS.items():
        if query_tokens.intersection(hints):
            inferred.append(tag)

    if not inferred and search_results:
        for _, record in search_results[:3]:
            for tag in record.tags:
                if tag not in inferred:
                    inferred.append(tag)

    if not inferred:
        inferred.extend(query_tokens)

    return inferred[:5] or ["general"]


def _format_api_results(query: str, matches: list[tuple[int, Path, str, str]]) -> str:
    if not matches:
        return (
            f'No local Godot API documentation matches were found for: "{query}".\n'
            "The local docs corpus may be missing, or the query may need to be more specific."
        )

    lines = [f'Godot API matches for: "{query}"', ""]
    for index, (score, path, title, summary) in enumerate(matches, start=1):
        lines.append(f"{index}. {path.as_posix()} (score: {score})")
        lines.append(f"   Title: {title}")
        lines.append(f"   Description: {summary}")
        lines.append("")
    lines.append("Use this as API knowledge only. Procedural skills belong in search_skills().")
    return "\n".join(lines).rstrip()


def _extract_markdown_title(text: str, path: Path) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def _extract_markdown_summary(text: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if len(paragraphs) > 1:
        return paragraphs[1].replace("\n", " ").strip()
    if paragraphs:
        return paragraphs[0].replace("\n", " ").strip()
    return ""


def _search_local_api_docs(query: str, limit: int = 5) -> list[tuple[int, Path, str, str]]:
    docs_dir = get_docs_dir()
    if not docs_dir.exists():
        return []

    query_text = query.lower().strip()
    query_tokens = _tokenize(query_text)
    if not query_text and not query_tokens:
        return []

    matches: list[tuple[int, Path, str, str]] = []
    for path in docs_dir.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # pragma: no cover - permissive local search
            continue

        title = _extract_markdown_title(text, path)
        summary = _extract_markdown_summary(text) or title
        haystack = " ".join([path.as_posix().lower(), title.lower(), summary.lower(), text.lower()])
        score = 0
        for token in query_tokens:
            if token in path.as_posix().lower():
                score += 2
            if token in title.lower():
                score += 3
            if token in summary.lower():
                score += 2
            if token in text.lower():
                score += 1
        if query_text and query_text in haystack:
            score += 2

        if score > 0:
            matches.append((score, path, title, summary))

    matches.sort(key=lambda item: (item[0], item[2].lower(), item[1].as_posix()), reverse=True)
    return matches[:limit]


@mcp.tool()
def list_skills() -> str:
    """
    Deprecated compatibility shim.

    The v2 workflow is retrieval-first; use search_skills(query) instead.
    """
    return _format_skill_listing(SKILL_INDEX.all_skills())


@mcp.tool()
def search_skills(query: str) -> str:
    """
    Search the skill index and return ranked procedural matches.

    Arguments:
        query: A natural language description of the task to accomplish.

    Returns references and summaries only. Never returns full file contents.
    """
    results = SKILL_INDEX.search(query, limit=SEARCH_RESULTS_LIMIT)
    return _format_search_results(query, results)


@mcp.tool()
def read_skill(skill_path: str) -> str:
    """
    Read a specific skill file from the /skills directory.

    The returned content is structured and includes metadata plus the full body.
    """
    try:
        skill_record = _load_skill_record(skill_path)
        return _render_skill_record(skill_record)
    except FileNotFoundError:
        return (
            f"Skill file not found: {skill_path}.\n"
            "Use search_skills(query) to discover indexed skills."
        )
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error accessing skill file: {str(exc)}"


@mcp.tool()
def create_skill(title: str, summary: str, tags: list[str], content: str) -> str:
    """
    Create a new skill file inside /skills.

    New skills must follow the v2 schema:
    # Title
    ## Summary
    ## Tags
    ## When to use
    ## Prerequisites
    ## Procedure
    ## Common mistakes
    ## Example
    ## Notes
    """
    ensure_skills_dir()
    target_path = build_skill_path(title)
    if target_path.exists():
        return f"Skill already exists: {target_path.name}"

    normalized_tags = _normalize_tags(tags)
    body = _render_skill_body(title.strip() or target_path.stem, summary, normalized_tags, content)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(body, encoding="utf-8")
    _clear_file_cache()
    SKILL_INDEX.refresh()
    logger.info("Created skill file %s", target_path)
    return f"Created skill: {target_path.relative_to(get_skills_dir()).as_posix()}"


@mcp.tool()
def update_skill(path: str, content: str, mode: str = "replace") -> str:
    """
    Update an existing skill file.

    mode:
        replace - overwrite the file body
        append - append under a new ## Additional Notes section
    """
    if mode.lower() not in UPDATE_MODES:
        return f"Invalid update mode: {mode}. Supported modes: replace, append."

    try:
        skill_file = validate_skill_path(path)
    except FileNotFoundError:
        return f"Skill file not found: {path}"
    except ValueError as exc:
        return str(exc)

    original_content = skill_file.read_text(encoding="utf-8")
    if mode.lower() == "replace":
        new_content = content.rstrip() + "\n"
    else:
        addition = content.strip()
        if original_content.endswith("\n"):
            separator = "\n"
        else:
            separator = "\n\n"
        new_content = (
            original_content.rstrip()
            + separator
            + "## Additional Notes\n"
            + addition
            + "\n"
        )

    skill_file.write_text(new_content, encoding="utf-8")
    _clear_file_cache()
    SKILL_INDEX.refresh()
    logger.info("Updated skill file %s with mode=%s", skill_file, mode.lower())
    return f"Updated skill: {skill_file.relative_to(get_skills_dir()).as_posix()} (mode={mode.lower()})"


@mcp.tool()
def search_api(query: str) -> str:
    """
    Search local Godot API documentation separately from procedural skills.

    MVP backend: scan the repo's local docs corpus if it is present.
    """
    matches = _search_local_api_docs(query)
    return _format_api_results(query, matches)


@mcp.tool()
def discover_missing_skill(task: str) -> str:
    """
    Suggest a new skill when the current index does not have a strong match.
    """
    matches = SKILL_INDEX.search(task, limit=SEARCH_RESULTS_LIMIT)
    top_score = matches[0][0] if matches else 0
    if top_score >= SKILL_MATCH_THRESHOLD:
        return (
            f"Existing skills already look relevant for: \"{task}\".\n"
            "Use search_skills(query) and read_skill(path) on the best matches before creating a new one."
        )

    title = sanitize_skill_name(task)
    inferred_tags = _infer_tags_for_task(task, matches)
    reason_parts = []
    if matches:
        reason_parts.append(f"best current match scored only {top_score}")
        reason_parts.append(f"closest match: {matches[0][1].path}")
    else:
        reason_parts.append("no indexed skill currently matches this task")

    return (
        "Proposed new skill:\n\n"
        f"title: {title}\n"
        f"reason: {'; '.join(reason_parts)}\n"
        f"recommended tags: {', '.join(inferred_tags)}\n"
        "next step: call create_skill() with a structured v2 body."
    )