"""Per-server session state: editor, services and the mandatory-plan gate."""

from __future__ import annotations

import json
from typing import Any

from ..config import get_settings
from ..editor import Editor
from ..errors import PlanRequiredError
from ..knowledge.storage import KnowledgeStore
from ..research.search import get_research_service
from ..workflows.planning import Plan


class Session:
    def __init__(self, editor: Editor | None = None, require_plan: bool | None = None):
        self.editor = editor or Editor()
        self.research = get_research_service()
        self.knowledge = KnowledgeStore()
        self.require_plan = get_settings().require_plan if require_plan is None else require_plan
        self.active_plan: Plan | None = None
        self.plan_history: list[Plan] = []
        self._attached: set[tuple[str, str]] = set()

    def check_plan(self, tool: str) -> None:
        if not self.require_plan:
            return
        if self.active_plan is None or self.active_plan.status != "active":
            raise PlanRequiredError(
                f"'{tool}' modifies an image, but no active plan exists.",
                hint="First show the user a numbered plan of at least 10 meaningful, request-specific steps and "
                     "register it with submit_plan (draft_plan can help). Then call this tool again.")

    def attach_plan(self, document_id: str | None) -> None:
        plan = self.active_plan
        if not plan or not document_id or (plan.id, document_id) in self._attached:
            return
        try:
            proj = self.editor.project(document_id)
        except Exception:
            return
        plan.document_id = plan.document_id or document_id
        path = proj.root / "plans" / f"{plan.id}.json"
        path.write_text(json.dumps(plan.model_dump(), indent=1, ensure_ascii=False), encoding="utf-8")
        if plan.id not in proj.manifest.plans:
            proj.manifest.plans.append(plan.id)
            proj.save()
        self._attached.add((plan.id, document_id))

    def plan_state(self) -> dict[str, Any]:
        return {"require_plan": self.require_plan,
                "active_plan": self.active_plan.model_dump() if self.active_plan else None}
