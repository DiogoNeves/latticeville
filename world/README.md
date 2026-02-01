## World maps

The world is defined in a single ASCII map file plus metadata in `world.json`.

Files:
- `world/world.map`: the full world grid.
- `world/world.json`: rooms (bounding boxes) + objects.
- `world/characters.json`: characters and starting rooms.

Legend (default):
- `#` wall (impassable)
- `.` floor (walkable)
- `+` door (walkable)
- `=` road/bridge (walkable)
- `~` water (impassable unless configured)
- `^` hazard (impassable unless configured)
- `*` generic object
- `T` tree
- `B` bench/boat
- `K` stall
- `S` shelf
- `@` character (agents are overlaid at runtime)

Rooms are axis-aligned rectangles defined in `world.json`. Each room should have
at least one entrance (an opening in the wall). Objects can be placed by explicit
`(x, y)` positions on the map and are treated as impassable for pathfinding.
