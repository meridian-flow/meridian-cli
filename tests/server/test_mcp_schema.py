import warnings
from typing import Any, cast

from pydantic import create_model
from pydantic.json_schema import PydanticJsonSchemaWarning

from meridian.lib.core.codec import signature_from_model
from meridian.lib.ops.spawn.models import SpawnCreateInput


def test_spawn_create_signature_model_json_schema_has_no_default_factory_warning() -> None:
    signature = signature_from_model(SpawnCreateInput)
    fields: dict[str, tuple[Any, Any]] = {}
    for name, parameter in signature.parameters.items():
        annotation = parameter.annotation if parameter.annotation is not parameter.empty else object
        default = parameter.default if parameter.default is not parameter.empty else ...
        fields[name] = (annotation, default)

    arg_model = create_model("SpawnCreateInputArgs", **cast("Any", fields))

    with warnings.catch_warnings():
        warnings.simplefilter("error", PydanticJsonSchemaWarning)
        schema = arg_model.model_json_schema()

    session_property = cast("dict[str, Any]", schema["properties"]["session"])
    assert isinstance(session_property.get("default"), dict)
