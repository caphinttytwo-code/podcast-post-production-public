# Inventory Manifest Schema

`inventory_project.py` reads a JSON configuration:

```json
{
  "schema_version": 1,
  "roots": [{"id": "project", "path": "/exact/project/path"}],
  "output_dir": "/separate/audit/path",
  "hash_mode": "all",
  "rules": {
    "retain": ["delivery/**", "versions/**"],
    "quarantine": ["work/cache/**"]
  }
}
```

`hash_mode` is `all`, `media`, or `none`. Classification is advisory: retain matches win, then explicit pending matches, then quarantine matches; unmatched files are pending. This ordering prevents a broad cleanup rule from overriding a protection rule.

Each file record contains root ID, absolute path, relative path, size, modification time, classification, optional SHA-256, and optional media probe data. The manifest records whether each field came from a current read.

Comparison reports contain added, removed, modified, and unchanged member sets. Backup reports match current source and backup records by relative path, size, and SHA-256; a missing hash cannot produce `hash_verified`.
