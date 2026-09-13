"""Prompt registrations for common optical-design workflows."""

from __future__ import annotations

from typing import Any


def register_prompts(server: Any) -> None:
    @server.prompt(  # type: ignore[untyped-decorator]
        name="zemax_analyze_system",
        description="Plan a concise quality review of the current optical system.",
    )
    def analyze_system(goal: str = "Assess image quality and identify dominant aberrations") -> str:
        return (
            f"Use the Zemax tools to {goal}. Begin with zemax_get_system, then select "
            "the smallest useful set of spot, MTF, ray/OPD fan, Seidel, color, field "
            "curvature, and illumination analyses. Report numeric findings and limitations."
        )

    @server.prompt(  # type: ignore[untyped-decorator]
        name="zemax_optimize_system",
        description="Plan a bounded, inspectable sequential optimization workflow.",
    )
    def optimize_system(goal: str, preserve: str = "existing focal length and packaging") -> str:
        return (
            f"Optimize the current Zemax design for: {goal}. Preserve: {preserve}. Inspect "
            "the prescription and variables first, build or review the merit function, apply "
            "physical bounds, optimize, then compare before/after metrics. Save only when asked."
        )

    @server.prompt(  # type: ignore[untyped-decorator]
        name="zemax_build_nsc_system",
        description="Plan a non-sequential illumination or stray-light workflow.",
    )
    def build_nsc_system(goal: str) -> str:
        return (
            f"Build or modify a non-sequential Zemax system for: {goal}. Inspect objects, "
            "configure sources/optics/detectors with explicit units, clear detectors, run an "
            "NSC ray trace, and verify detector totals and peak data before reporting completion."
        )
