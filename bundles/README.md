# Bundles and specs

This directory is mounted read-only into the service at `/data/bundles`. The service only reads
bundle names relative to that path and refuses anything that escapes it, so keep every bundle and
the spec files it references here.

```
bundles/
  stripe-v2500-v2596.json    # a T10b migration bundle
  specs/
    stripe-v2500.json        # the old OpenAPI document
    stripe-v2596.json        # the new OpenAPI document
```

Mounting is read-only: `./bundles:/data/bundles:ro`. Put the paths inside a bundle in the container
form (`/data/bundles/specs/...`) or relative to the bundle file, and queue a run with
`POST /runs {"bundle": "stripe-v2500-v2596.json"}`.

Everything under this directory except this README is gitignored; bundles and specs are operator
input, so back them up with the host if they are not reproducible.
