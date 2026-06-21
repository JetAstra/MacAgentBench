"""Fine-grained evaluation result data classes.

This module defines :class:`EvalResult` and :class:`EvalComponent`, the
return type of the fine-grained evaluation path in
``controllers.env.MacOSEnv.evaluate_task``.

Backward compatibility:

- ``bool(result)``  → returns ``result.completed`` (strict, == 1.0)
- ``float(result)`` → returns ``result.score``      (continuous, [0, 1])
- ``str(result)``   → short summary

Tasks without ``scoring_components`` continue to receive a plain ``bool``
from ``evaluate_task`` — this module is *only* used for tasks that opt
into fine-grained evaluation by declaring ``scoring_components`` in their
task JSON.

See ``FINE_GRAINED_EVAL_DESIGN.md`` at the project root for the full
schema specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EVAL_SCHEMA_VERSION = "1.0"


@dataclass
class EvalComponent:
    """A single weighted checkpoint in a fine-grained evaluation."""

    name: str
    weight: float
    capability: str
    score: float
    func: str
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weight": self.weight,
            "capability": self.capability,
            "score": self.score,
            "func": self.func,
            "parameters": self.parameters,
            "raw_output": self.raw_output,
        }


@dataclass
class EvalResult:
    """The fine-grained result of evaluating a single task.

    Use :meth:`to_result_txt` to serialise this object to the on-disk
    ``result.txt`` schema (which also includes ``steps_used`` and
    ``max_steps`` from the runner).
    """

    task_id: str
    components: list[EvalComponent] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Derived properties
    # ------------------------------------------------------------------ #

    @property
    def score(self) -> float:
        """Weighted sum of component scores, in ``[0, 1]``."""
        return sum(c.weight * c.score for c in self.components)

    @property
    def completed(self) -> bool:
        """Strict completion: ``True`` iff every component scored 1.0."""
        # Use math.isclose to be safe against float drift, but stay
        # consistent with the documented "score == 1.0" semantics.
        return self.score >= 1.0 - 1e-9

    @property
    def n_checkpoints(self) -> int:
        return len(self.components)

    @property
    def n_checkpoints_passed(self) -> int:
        """Number of components that scored exactly 1.0 (strict)."""
        return sum(1 for c in self.components if c.score >= 1.0 - 1e-9)

    # ------------------------------------------------------------------ #
    # Backward-compat dunders
    # ------------------------------------------------------------------ #

    def __bool__(self) -> bool:
        return self.completed

    def __float__(self) -> float:
        return self.score

    def __str__(self) -> str:
        return (
            f"EvalResult(task={self.task_id!r}, score={self.score:.3f}, "
            f"completed={self.completed}, "
            f"checkpoints={self.n_checkpoints_passed}/{self.n_checkpoints})"
        )

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #

    def to_result_txt(self, steps_used: int, max_steps: int) -> dict:
        """Build the ``result.txt`` payload (legacy fields first).

        The field order matches ``FINE_GRAINED_EVAL_DESIGN.md`` §4 so
        that the JSON file remains human-readable.
        """
        return {
            # Legacy fields (must come first for backward compat)
            "completed": self.completed,
            "steps_used": steps_used,
            "max_steps": max_steps,
            # Fine-grained fields
            "eval_schema_version": EVAL_SCHEMA_VERSION,
            "task_id": self.task_id,
            "score": round(self.score, 4),
            "n_checkpoints": self.n_checkpoints,
            "n_checkpoints_passed": self.n_checkpoints_passed,
            "components": [c.to_dict() for c in self.components],
        }
