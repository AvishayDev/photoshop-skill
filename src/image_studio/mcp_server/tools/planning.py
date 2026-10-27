from __future__ import annotations

from typing import Any

from ...core.capabilities import capability_report
from ...errors import ValidationError
from ...workflows.planning import draft_plan as _draft
from ...workflows.planning import make_plan


def register(tool, session) -> None:
    @tool(read_only=True, title="Capabilities")
    def get_capabilities(include_gimp_filters: bool = False) -> dict[str, Any]:
        """Report which backends are installed (built-in raster engine, GIMP 3, Photoshop), which operations
        are available and their known limitations. Call this before planning so the plan never relies on an
        unavailable operation. include_gimp_filters lists GEGL operations (starts GIMP, ~5-15 s)."""
        from ...patterns import PatternLibrary
        from ...pipeline.spec import ACTIONS
        rep = capability_report(check_gimp_filters=include_gimp_filters)
        rep["painting"] = {"actions": sorted(ACTIONS), "pattern_library": len(PatternLibrary().all()),
                           "note": "Images are created by painting (no generative model). Write Python pipelines "
                                   "with image_studio.pipeline.Pipeline or use paint_layer / run_pipeline."}
        rep["research_providers"] = session.research.list_providers()
        rep["plan_gate"] = session.plan_state()
        return {"ok": True, **rep}

    @tool(read_only=True, title="Draft a plan")
    def draft_plan(request: str, document_id: str | None = None) -> dict[str, Any]:
        """Suggest a request-specific plan (>= 10 steps) to adapt. It is a starting point: rewrite steps
        so they fit the actual request and context, show the numbered plan to the user, then submit_plan."""
        return {"ok": True, **_draft(request, {"document_id": document_id})}

    @tool(title="Submit the plan")
    def submit_plan(request: str, steps: list[str], document_id: str | None = None) -> dict[str, Any]:
        """Register the numbered plan you have shown to the user (>= 10 distinct, meaningful steps covering
        understanding, the edits, visual verification, and saving/exporting). Required before any tool that
        modifies an image. Replaces a previous active plan."""
        plan, warnings = make_plan(request, steps, document_id)
        if session.active_plan and session.active_plan.status == "active":
            session.active_plan.status = "superseded"
            session.plan_history.append(session.active_plan)
        session.active_plan = plan
        if document_id:
            session.attach_plan(document_id)
        return {"ok": True, "plan_id": plan.id, "step_count": len(plan.steps), "warnings": warnings,
                "plan_markdown": plan.as_markdown(),
                "next": "Proceed with the steps. Re-plan with submit_plan if the request changes substantially."}

    @tool(read_only=True, title="Current plan")
    def get_plan() -> dict[str, Any]:
        """Return the active plan (if any) and whether the plan gate is enforced."""
        return {"ok": True, **session.plan_state()}

    @tool(title="Complete the plan")
    def complete_plan(summary: str, unresolved_issues: list[str] | None = None) -> dict[str, Any]:
        """Mark the active plan finished after delivering the result. A new request needs a new plan."""
        plan = session.active_plan
        if not plan:
            raise ValidationError("No active plan")
        plan.status = "completed"
        plan.notes = summary + ("\nUnresolved: " + "; ".join(unresolved_issues) if unresolved_issues else "")
        if plan.document_id:
            session._attached.discard((plan.id, plan.document_id))
            session.attach_plan(plan.document_id)
        session.plan_history.append(plan)
        session.active_plan = None
        return {"ok": True, "plan_id": plan.id, "status": "completed",
                "reminder": "Save genuinely reusable lessons with save_knowledge."}
