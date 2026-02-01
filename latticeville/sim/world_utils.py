"""World tree helpers for resolving hierarchical locations."""

from __future__ import annotations

from latticeville.sim.contracts import NodeType, WorldTree


def resolve_area_id(world: WorldTree, node_id: str | None) -> str | None:
    if node_id is None:
        return None
    current = node_id
    while current is not None:
        node = world.nodes.get(current)
        if node is None:
            return None
        if node.type == NodeType.AREA:
            return node.id
        current = node.parent_id
    return None


def resolve_area_name(world: WorldTree, node_id: str | None) -> str | None:
    area_id = resolve_area_id(world, node_id)
    if area_id is None:
        return None
    node = world.nodes.get(area_id)
    return node.name if node else None
