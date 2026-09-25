import enum
import inspect

from app.models import models


def test_all_models_enums_have_lowercase_values():
    enum_classes = [
        obj
        for name, obj in inspect.getmembers(models, inspect.isclass)
        if issubclass(obj, enum.Enum) and obj is not enum.Enum
    ]

    assert len(enum_classes) > 0, "Expected at least one Enum class in app.models.models"

    for enum_cls in enum_classes:
        for member in enum_cls:
            val = member.value
            assert isinstance(val, str), f"{enum_cls.__name__}.{member.name} value is not a string: {val}"
            assert val == val.lower(), (
                f"{enum_cls.__name__}.{member.name} value '{val}' is not lowercase. "
                "All model enum values must be lowercase to maintain PostgreSQL compatibility."
            )
