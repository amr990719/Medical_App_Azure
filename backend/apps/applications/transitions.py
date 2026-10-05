"""THE status transition table (PROMPT.md §16.2).

Any pair not listed is rejected with INVALID_STATUS_TRANSITION.
"""

from dataclasses import dataclass

from apps.accounts.models import Role
from apps.reference.constants import ApplicationStatus as S


@dataclass(frozen=True)
class Transition:
    actor_role: Role
    requires_notes: bool = False
    requires_payment_confirmed: bool = False


ALLOWED: dict[tuple[str, str], Transition] = {
    # Doctor: submission runs full validation, freezes the fee and assigns the reference number.
    (S.DRAFT, S.SUBMITTED): Transition(Role.DOCTOR),
    (S.NEEDS_CORRECTION, S.SUBMITTED): Transition(Role.DOCTOR),
    # Admin review.
    (S.SUBMITTED, S.UNDER_REVIEW): Transition(Role.ADMIN),
    (S.SUBMITTED, S.NEEDS_CORRECTION): Transition(Role.ADMIN, requires_notes=True),
    (S.UNDER_REVIEW, S.NEEDS_CORRECTION): Transition(Role.ADMIN, requires_notes=True),
    (S.UNDER_REVIEW, S.APPROVED): Transition(Role.ADMIN, requires_payment_confirmed=True),
    (S.SUBMITTED, S.REJECTED): Transition(Role.ADMIN, requires_notes=True),
    (S.UNDER_REVIEW, S.REJECTED): Transition(Role.ADMIN, requires_notes=True),
}


def allowed_targets(status: str, *, role: str) -> list[str]:
    """Targets reachable from `status` by `role` — drives the admin transition buttons."""
    return [to for (frm, to), rule in ALLOWED.items() if frm == status and rule.actor_role == role]
