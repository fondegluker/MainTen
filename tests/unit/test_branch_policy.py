"""Unit test for branch naming regex compliance."""

import re

BRANCH_NAME_REGEX = r"^(iteration-[0-9]+(-hotfix)?|jules-[A-Za-z0-9_-]+)$"


def is_valid_branch_name(branch_name: str) -> bool:
    """Validate branch name against relaxed branch policy regex."""
    return bool(re.match(BRANCH_NAME_REGEX, branch_name))


def test_valid_branch_names():
    """Verify regex accepts valid iteration and jules branch names."""
    valid_names = [
        "iteration-1",
        "iteration-10",
        "iteration-3-hotfix",
        "jules-3805668974257506057-99790dda",
        "jules-abc_123",
    ]
    for name in valid_names:
        assert is_valid_branch_name(name), f"Expected '{name}' to be valid"


def test_invalid_branch_names():
    """Verify regex rejects non-conforming branch names."""
    invalid_names = [
        "feat/iteration-3",
        "iteration_3",
        "iteration",
        "iteration-",
        "Iteration-3",
        "main",
        "dev",
    ]
    for name in invalid_names:
        assert not is_valid_branch_name(name), f"Expected '{name}' to be invalid"
