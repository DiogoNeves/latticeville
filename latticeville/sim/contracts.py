"""Core data contracts and validation stubs for Phase 0."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)


class NodeType(str, Enum):
    AREA = "area"
    OBJECT = "object"
    AGENT = "agent"


class WorldNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: NodeType
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)


class WorldTree(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_id: str
    nodes: dict[str, WorldNode]

    @model_validator(mode="after")
    def validate_tree(self) -> "WorldTree":
        if self.root_id not in self.nodes:
            raise ValueError("root_id must exist in nodes")
        for node_id, node in self.nodes.items():
            if node.id != node_id:
                raise ValueError("node id must match nodes key")
        return self


class BeliefTree(WorldTree):
    """Per-agent belief tree (partial/stale allowed)."""


class StateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world: WorldTree
    beliefs: dict[str, BeliefTree] = Field(default_factory=dict)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TickPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tick: int
    state: StateSnapshot
    events: list[Event] | None = None


class ActionKind(str, Enum):
    IDLE = "IDLE"
    MOVE = "MOVE"
    INTERACT = "INTERACT"
    SAY = "SAY"


class InteractVerb(str, Enum):
    USE = "USE"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    TAKE = "TAKE"
    DROP = "DROP"


class MoveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_location_id: str


class InteractArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: str
    verb: InteractVerb


class SayArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_agent_id: str
    utterance: str


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ActionKind
    move: MoveArgs | None = None
    interact: InteractArgs | None = None
    say: SayArgs | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "Action":
        if self.kind == ActionKind.MOVE:
            if self.move is None or self.interact is not None or self.say is not None:
                raise ValueError("MOVE requires move args only")
        elif self.kind == ActionKind.INTERACT:
            if self.interact is None or self.move is not None or self.say is not None:
                raise ValueError("INTERACT requires interact args only")
        elif self.kind == ActionKind.SAY:
            if self.say is None or self.move is not None or self.interact is not None:
                raise ValueError("SAY requires say args only")
        else:
            if (
                self.move is not None
                or self.interact is not None
                or self.say is not None
            ):
                raise ValueError("IDLE cannot include args")
        return self


@dataclass(frozen=True)
class ValidTargets:
    locations: set[str] = field(default_factory=set)
    objects: set[str] = field(default_factory=set)
    agents: set[str] = field(default_factory=set)


def coerce_action(raw: Any, valid_targets: ValidTargets | None = None) -> Action:
    """Validate an action or fall back to IDLE."""
    try:
        action = Action.model_validate(raw)
    except ValidationError:
        return Action(kind=ActionKind.IDLE)

    if valid_targets is None:
        return action

    if action.kind == ActionKind.MOVE:
        if (
            action.move is None
            or action.move.to_location_id not in valid_targets.locations
        ):
            return Action(kind=ActionKind.IDLE)
    elif action.kind == ActionKind.INTERACT:
        if (
            action.interact is None
            or action.interact.object_id not in valid_targets.objects
        ):
            return Action(kind=ActionKind.IDLE)
    elif action.kind == ActionKind.SAY:
        if action.say is None or action.say.to_agent_id not in valid_targets.agents:
            return Action(kind=ActionKind.IDLE)

    return action
