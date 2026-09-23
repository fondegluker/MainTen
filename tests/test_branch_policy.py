"""Unit test for iteration branch naming regex compliance."""

import re

BRANCH_NAME_REGEX = r"^iteration-[0-9]+(-hotfix)?$"


def is_valid_branch_name(branch_name: str) -> bool:
    """Validate branch name against strict iteration branch policy regex."""
    return bool(re.match(BRANCH_NAME_REGEX, branch_name))


def test_valid_branch_names():
    """Verify regex accepts valid iteration branch names."""
    valid_names = [
        "iteration-1",
        "iteration-2",
        "iteration-3",
        "iteration-10",
        "iteration-1-hotfix",
        "iteration-3-hotfix",
    ]
    for name in valid_names:
        assert is_valid_branch_name(name), f"Expected '{name}' to be valid"


def test_invalid_branch_names():
    """Verify regex rejects non-conforming branch names."""
    invalid_names = [
        "feat/iteration-3",
        "jules/iteration-3",
        "iteration_3",
        "iteration",
        "iteration-",
        "Iteration-3",
        "jules-12345-abc",
        "jules-3805668974257506057-99790dda",
        "master",
        "dev",
        "iteration-3-v2",
    ]
    for name in invalid_names:
        assert not is_valid_branch_name(name), f"Expected '{name}' to be invalid"
