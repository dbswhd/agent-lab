from __future__ import annotations


def test_plan_package_submodule_import() -> None:
    from agent_lab.plan import workflow
    from agent_lab.plan.workflow import get_plan_workflow

    assert workflow.get_plan_workflow is get_plan_workflow


def test_plan_package_symbol_reexport() -> None:
    from agent_lab.plan import (
        PlanAction,
        PlanWorkflowNotApproved,
        get_plan_workflow,
        run_dry_run,
    )
    from agent_lab.plan.actions import PlanAction as PlanActionDirect
    from agent_lab.plan.execute import run_dry_run as run_dry_run_direct
    from agent_lab.plan.workflow import (
        PlanWorkflowNotApproved as PlanWorkflowNotApprovedDirect,
    )
    from agent_lab.plan.workflow import get_plan_workflow as get_plan_workflow_direct

    assert PlanAction is PlanActionDirect
    assert PlanWorkflowNotApproved is PlanWorkflowNotApprovedDirect
    assert get_plan_workflow is get_plan_workflow_direct
    assert run_dry_run is run_dry_run_direct
