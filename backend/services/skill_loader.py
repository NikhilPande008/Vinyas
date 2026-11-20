"""Vinyas — Progressive Disclosure Agent Skill Loader (`backend/services/skill_loader.py`).

Implements the `agentskills.io` Progressive Disclosure pattern:
1. At startup, scans `/.agents/skills/*/SKILL.md` and loads ONLY the YAML frontmatter
   (`name` and `description`) into memory.
2. When an inspection anomaly escalates to Tier-2, dynamically loads the full `SKILL.md`
   markdown body and any `references/*.md` files for the matching domain skill.
3. Provides deterministic SQL guardrail validation enforcing `ops-db-guardrails`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any, Optional

from backend.config import PROJECT_ROOT


SKILLS_ROOT = PROJECT_ROOT / ".agents" / "skills"

SCENARIO_TO_SKILL_MAP = {
    "LINE_A_PCB": "pcb-defect-triage",
    "LINE_B_CNC": "bearing-acoustic-diagnostics",
    "LINE_C_WELD": "maintenance-work-order",
    "LINE_D_HEALTHY": "ops-db-guardrails",
}


@dataclass
class SkillDescriptor:
    """Lightweight startup skill metadata (Progressive Disclosure Stage 1)."""

    name: str
    description: str
    skill_dir: Path
    full_body_loaded: bool = False
    activation_count: int = 0
    cached_body: Optional[str] = None
    cached_references: dict[str, str] = field(default_factory=dict)


def _parse_frontmatter_only(skill_md_path: Path) -> tuple[str, str]:
    """Extract only `name` and `description` from YAML frontmatter without loading the body."""
    raw = skill_md_path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", raw, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Missing YAML frontmatter in {skill_md_path}")
    frontmatter = match.group(1)

    name_match = re.search(r"^name:\s*(.+)$", frontmatter, flags=re.MULTILINE)
    desc_match = re.search(r"^description:\s*(.+)$", frontmatter, flags=re.MULTILINE)
    if not name_match or not desc_match:
        raise ValueError(f"Missing required name or description in {skill_md_path}")

    name = name_match.group(1).strip().strip("\"'")
    description = desc_match.group(1).strip().strip("\"'")

    if not re.match(r"^[a-z0-9-]+$", name) or len(name) > 64:
        raise ValueError(f"Invalid skill name '{name}': must be lowercase-kebab-case <= 64 chars")
    if name != skill_md_path.parent.name:
        raise ValueError(
            f"Skill name '{name}' must match directory name '{skill_md_path.parent.name}'"
        )
    if len(description) >= 1024:
        raise ValueError(f"Skill description for '{name}' exceeds 1024 characters")

    return name, description


class ProgressiveSkillLoader:
    """Manages progressive disclosure of `.agents/skills/` domain skills."""

    def __init__(self, skills_root: Path = SKILLS_ROOT) -> None:
        self.skills_root = skills_root
        self._registry: dict[str, SkillDescriptor] = {}
        self.discover_metadata_only()

    def discover_metadata_only(self) -> dict[str, SkillDescriptor]:
        """Stage 1: Load ONLY `name` + `description` frontmatter for all skills."""
        self._registry.clear()
        if not self.skills_root.exists():
            return self._registry

        for skill_md in sorted(self.skills_root.glob("*/SKILL.md")):
            name, description = _parse_frontmatter_only(skill_md)
            self._registry[name] = SkillDescriptor(
                name=name,
                description=description,
                skill_dir=skill_md.parent,
                full_body_loaded=False,
                activation_count=0,
            )
        return self._registry

    def list_skills_status(self) -> list[dict[str, Any]]:
        """Return progressive disclosure telemetry for the UI Architecture Modal."""
        return [
            {
                "name": desc.name,
                "description": desc.description,
                "full_body_loaded": desc.full_body_loaded,
                "activation_count": desc.activation_count,
                "references_loaded": list(desc.cached_references.keys()),
            }
            for desc in self._registry.values()
        ]

    def activate_skill_for_scenario(self, scenario_key: str) -> dict[str, Any]:
        """Stage 2: Dynamically load full `SKILL.md` + `references/*.md` on demand."""
        skill_name = SCENARIO_TO_SKILL_MAP.get(scenario_key, "maintenance-work-order")
        return self.load_full_skill(skill_name)

    def load_full_skill(self, skill_name: str) -> dict[str, Any]:
        """Load full markdown body and reference files for a specific skill."""
        if skill_name not in self._registry:
            self.discover_metadata_only()
        descriptor = self._registry[skill_name]

        skill_md_path = descriptor.skill_dir / "SKILL.md"
        full_text = skill_md_path.read_text(encoding="utf-8")
        lines = full_text.splitlines()
        if len(lines) >= 500:
            raise ValueError(f"SKILL.md for {skill_name} exceeds 500 lines ({len(lines)})")

        refs_dir = descriptor.skill_dir / "references"
        references: dict[str, str] = {}
        if refs_dir.exists():
            for ref_file in sorted(refs_dir.glob("*.md")):
                references[ref_file.name] = ref_file.read_text(encoding="utf-8")

        descriptor.full_body_loaded = True
        descriptor.activation_count += 1
        descriptor.cached_body = full_text
        descriptor.cached_references = references

        return {
            "name": descriptor.name,
            "description": descriptor.description,
            "full_body_loaded": True,
            "activation_count": descriptor.activation_count,
            "skill_markdown": full_text,
            "references": references,
        }


def validate_sql_against_guardrails(sql_text: str) -> tuple[bool, list[str]]:
    """Enforce `ops-db-guardrails` rules on DDL or query strings."""
    violations: list[str] = []

    if re.search(r"\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\s+TABLE)\b", sql_text, flags=re.IGNORECASE):
        violations.append("Destructive DDL (DROP TABLE / DROP DATABASE / TRUNCATE TABLE) is prohibited.")

    cleaned_for_interp = re.sub(r"DO\s+\$\$.*?\$\$\s*;", "", sql_text, flags=re.DOTALL | re.IGNORECASE)
    if re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", cleaned_for_interp):
        violations.append("Raw Python f-string interpolation detected; use parameterized $1 or ? bindings.")

    create_matches = re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s*\((.*?)\);",
        sql_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    for match in create_matches:
        table_name = match.group(1)
        columns_block = match.group(2)
        if not re.match(r"^[a-z][a-z0-9_]*$", table_name):
            violations.append(f"Table name '{table_name}' violates snake_case convention.")
        if not re.search(r"\bid\b[^,]*PRIMARY\s+KEY", columns_block, flags=re.IGNORECASE):
            violations.append(f"Table '{table_name}' is missing mandatory 'id ... PRIMARY KEY'.")

    return len(violations) == 0, violations


_SKILL_LOADER_SINGLETON: Optional[ProgressiveSkillLoader] = None


def get_skill_loader() -> ProgressiveSkillLoader:
    global _SKILL_LOADER_SINGLETON
    if _SKILL_LOADER_SINGLETON is None:
        _SKILL_LOADER_SINGLETON = ProgressiveSkillLoader()
    return _SKILL_LOADER_SINGLETON
