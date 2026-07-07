# releases/

Build output goes here (git-ignored). Generate with:

```bash
python scripts/build_release.py
```

Produces `redforge-<version>/` (self-contained, no Node.js) plus
`redforge-<version>.zip` and `.tar.gz`. Native installers are built from this
folder — see `../installers/`.
