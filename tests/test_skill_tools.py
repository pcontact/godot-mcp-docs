from pathlib import Path

import pytest

from srcs.tools import skill_tools
from srcs.utils import docs_utils, skill_utils
from srcs.utils.skill_index import SkillIndex, parse_skill_file


@pytest.fixture()
def isolated_skill_env(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    monkeypatch.setattr(skill_utils, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(skill_tools, "SKILL_INDEX", SkillIndex(skills_dir))
    return skills_dir


def _write_skill(path: Path, title: str, summary: str, tags: str, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                "## Summary",
                summary,
                "",
                "## Tags",
                tags,
                "",
                "## When to use",
                "Use this when the workflow matches.",
                "",
                "## Prerequisites",
                "- None",
                "",
                "## Procedure",
                content,
                "",
                "## Common mistakes",
                "- Mistake one",
                "",
                "## Example",
                "- Example one",
                "",
                "## Notes",
                "- Notes",
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_search_skills_ranks_relevant_skills(isolated_skill_env):
    _write_skill(
        isolated_skill_env / "movement" / "chase_player.txt",
        "Chase Player",
        "NPC follows the target using NavigationAgent3D.",
        "movement, navigation, ai",
        "Follow the player using pathfinding and steering.",
    )
    _write_skill(
        isolated_skill_env / "ai" / "enemy_ai.txt",
        "Enemy AI",
        "Basic enemy decision loop.",
        "ai, combat",
        "Choose between patrol, attack, and retreat.",
    )
    skill_tools.SKILL_INDEX.refresh()

    result = skill_tools.search_skills("make enemy chase player in 3D")

    assert "movement/chase_player.txt" in result
    assert result.index("movement/chase_player.txt") < result.index("ai/enemy_ai.txt")
    assert "NPC follows the target" in result
    assert "Follow the player using pathfinding and steering." not in result


def test_search_skills_returns_no_full_file_contents_when_irrelevant(isolated_skill_env):
    _write_skill(
        isolated_skill_env / "movement" / "jump.txt",
        "Jump",
        "Vertical movement helper.",
        "movement",
        "UNIQUE_SENTINEL_DO_NOT_LEAK",
    )
    skill_tools.SKILL_INDEX.refresh()

    result = skill_tools.search_skills("enemy behavior")

    assert "UNIQUE_SENTINEL_DO_NOT_LEAK" not in result


def test_create_skill_writes_standard_schema_and_normalizes_filename(isolated_skill_env):
    result = skill_tools.create_skill(
        "Wall Climb System",
        "Support vertical traversal on ledges and walls.",
        ["Movement", "Traversal", "Physics"],
        "Detect climbable surfaces and advance the player upward.",
    )

    created = isolated_skill_env / "wall-climb-system.txt"
    assert created.exists()
    parsed = parse_skill_file(created)
    content = created.read_text(encoding="utf-8")

    assert result == "Created skill: wall-climb-system.txt"
    assert "# Wall Climb System" in content
    assert "## Summary" in content
    assert "## Tags" in content
    assert "## Procedure" in content
    assert "movement, traversal, physics" in content
    assert parsed["title"] == "Wall Climb System"
    assert parsed["summary"] == "Support vertical traversal on ledges and walls."
    assert parsed["tags"] == ["movement", "traversal", "physics"]


def test_update_skill_replace_and_append(isolated_skill_env):
    created = skill_tools.create_skill(
        "Enemy Patrol",
        "Patrol behavior for AI enemies.",
        ["ai", "movement"],
        "Walk between points and pause at each node.",
    )
    assert "Created skill" in created

    replace_result = skill_tools.update_skill(
        "enemy-patrol.txt",
        "# Enemy Patrol\n\n## Summary\nUpdated patrol loop.\n",
        mode="replace",
    )
    append_result = skill_tools.update_skill(
        "enemy-patrol.txt",
        "Add a fallback when the route is blocked.",
        mode="append",
    )

    content = (isolated_skill_env / "enemy-patrol.txt").read_text(encoding="utf-8")
    assert "mode=replace" in replace_result
    assert "mode=append" in append_result
    assert "Updated patrol loop." in content
    assert "## Additional Notes" in content
    assert "Add a fallback when the route is blocked." in content


def test_read_skill_returns_structured_output(isolated_skill_env):
    skill_tools.create_skill(
        "Target Lock",
        "Keep a target centered in view.",
        ["camera", "ui"],
        "Rotate the camera toward the target.",
    )

    output = skill_tools.read_skill("target-lock.txt")

    assert "Title: Target Lock" in output
    assert "Summary: Keep a target centered in view." in output
    assert "Path: target-lock.txt" in output
    assert "Content:" in output


def test_discover_missing_skill_suggests_new_skill(isolated_skill_env):
    result = skill_tools.discover_missing_skill("grappling hook system")

    assert "Proposed new skill" in result
    assert "grappling-hook-system" in result
    assert "recommended tags" in result


def test_search_api_uses_local_docs_when_available(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    monkeypatch.setattr(docs_utils, "DOCS_DIR", docs_dir)

    doc_file = docs_dir / "classes" / "character_body3d.md"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text(
        "\n".join(
            [
                "# CharacterBody3D",
                "",
                "A 3D body for player and enemy movement.",
                "",
                "move_and_slide() moves the body based on velocity.",
            ]
        ),
        encoding="utf-8",
    )

    result = skill_tools.search_api("move_and_slide")

    assert "Godot API matches" in result
    assert "classes/character_body3d.md" in result
    assert "move_and_slide" in result


def test_list_skills_is_deprecated_but_still_available(isolated_skill_env):
    skill_tools.create_skill(
        "Signal Relay",
        "Connect gameplay signals across systems.",
        ["events", "systems"],
        "Forward relevant signals to listeners.",
    )

    output = skill_tools.list_skills()

    assert "Deprecated" in output
    assert "signal-relay.txt" in output
