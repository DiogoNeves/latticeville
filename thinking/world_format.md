# World data format

This doc defines the world data files in `world/` and how the simulation loads them.

## Files

- `world/world.json`: Areas, portals, and objects.
- `world/characters.json`: Character roster and starting locations.
- `world/<area_id>.map`: ASCII map per area.
- `world/README.md`: Map legend and defaults.

## Map rules

- Each area has a `<area_id>.map` ASCII file.
- Portals use digits `1-9` and are **local** to the area.
- Portal destinations are defined in `world.json` (not in the map).
- Objects may be placed by map tile or explicit `(x, y)` position.
- Characters are overlaid at runtime; `@` is the default glyph.

## world.json schema (informal)

```
{
  "areas": [
    {
      "id": "street",
      "name": "Neon Street",
      "map_file": "street.map",
      "portals": { "1": "cafe", "2": "park" }
    }
  ],
  "objects": [
    {
      "id": "bench",
      "name": "Bench",
      "area_id": "park",
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
      "start_area_id": "street",
      "patrol_route": ["street", "park"]
    }
  ]
}
```
