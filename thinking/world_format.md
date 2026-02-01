# World data format

This doc defines the world data files in `world/` and how the simulation loads them.

## Files

- `world/world.json`: Rooms (bounding boxes) and objects.
- `world/characters.json`: Character roster and starting locations.
- `world/world.map`: Single ASCII map for the entire world.
- `world/README.md`: Map legend and defaults.

## Map rules

- The world uses a single `world.map` ASCII file.
- Rooms are axis-aligned rectangles defined in `world.json`.
- Rooms must have at least one open entrance in the surrounding wall.
- Objects may be placed by map tile or explicit `(x, y)` position.
- Characters are overlaid at runtime; `@` is the default glyph.

## world.json schema (informal)

```
{
  "map_file": "world.map",
  "rooms": [
    {
      "id": "cafe",
      "name": "Cafe",
      "bounds": { "x": 10, "y": 4, "width": 8, "height": 6 }
    }
  ],
  "objects": [
    {
      "id": "bench",
      "name": "Bench",
      "room_id": "park",
      "symbol": "B",
      "position": { "x": 6, "y": 3 }
    }
  ]
}
```

## characters.json schema (informal)

```
{
  "characters": [
    {
      "id": "ada",
      "name": "Ada",
      "symbol": "@",
      "start_room_id": "street",
      "patrol_route": ["street", "park"]
    }
  ]
}
```
