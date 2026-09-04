"""Requests for documented SDK operations and native feature editing."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from .models import Model, Positive

Name = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$", max_length=120)]


class ApiStep(Model):
    id: Name
    target: JsonValue
    member: Name
    action: Literal["call", "get", "set"] = "call"
    arguments: list[JsonValue] = Field(default_factory=list)
    value: JsonValue = None
    expect: Literal["any", "truthy", "not_null"] = "any"


class ApiBatch(Model):
    steps: Annotated[list[ApiStep], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def references_are_ordered(self):
        seen: set[str] = set()

        def check(value):
            if isinstance(value, dict):
                if set(value) == {"ref"} and value["ref"] not in seen:
                    raise ValueError(f"Unknown/forward batch reference: {value['ref']}")
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"Duplicate step id: {step.id}")
            for value in (step.target, step.arguments, step.value):
                check(value)
            seen.add(step.id)
        return self


class DefinitionCall(Model):
    # Zero-argument getters navigating from a feature definition, e.g. ['array'].
    via: list[Name] = Field(default_factory=list, max_length=5)
    member: Name
    arguments: list[JsonValue] = Field(default_factory=list)
    expect: Literal["any", "truthy", "not_null"] = "truthy"


class FeatureSettings(Model):
    properties: dict[Name, JsonValue] = Field(default_factory=dict)
    calls: list[DefinitionCall] = Field(default_factory=list, max_length=100)


class EdgeTreatment(Model):
    kind: Literal["fillet", "chamfer"]
    edges: Annotated[list[str], Field(min_length=1, max_length=1000)]
    size: Positive
    second_size: Positive | None = None
    tangent: bool = False
    name: str = "Edge treatment"
