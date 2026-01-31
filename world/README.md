## World maps

Each area has a `<area_name>.map` ASCII file. Portals are digits `1-9` and are local
to the area. The actual portal destinations are defined in `world.json`.

Legend (default):
- `#` wall
- `.` floor
- `+` door
- `=` road/bridge
- `~` water
- `^` hazard
- `*` generic object
- `T` tree
- `B` bench
- `@` character (agents are overlaid at runtime)
- `1-9` portal tiles (local to the area)

Objects can override symbols in `world.json`.
