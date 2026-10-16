# Development ownership

The maintainer workspace for this project is on the home Mac mini, reached
through the SSH alias `mac-1`, at `~/psyhitech/ha-fordpass-china`.

- Perform project edits, tests, commits and pushes in that workspace.
- A copy inside the separate home-kiosk repository on a MacBook is historical;
  do not develop there or sync it over this repository.
- GitHub is the shared source history. The Home Assistant installed component
  is a deployment copy, not the source workspace.
- Keep credentials, VINs, locations, captures, APKs, native vendor libraries,
  white-box keys and runtime databases outside Git.
- Keep the standalone protocol and the component's protocol sources identical;
  run `python scripts/check_protocol_sync.py` after protocol changes.
- Run the tests with a Home Assistant-capable Python environment before deploying.
- Do not send vehicle commands as part of tests or deployments.
