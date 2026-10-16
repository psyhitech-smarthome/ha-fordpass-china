# Maintainer workflow

Development, testing and GitHub operations take place on the home Mac mini.
The laptop is only the SSH client.

```sh
ssh mac-1
cd ~/psyhitech/ha-fordpass-china
git status --short --branch
```

For the currently installed Home Assistant development environment:

```sh
~/ha-core/.venv-2026.10.1/bin/python scripts/check_protocol_sync.py
~/ha-core/.venv-2026.10.1/bin/python -m unittest discover -s tests -v
git diff --check
```

Use the environment corresponding to the installed HA version when HA is
upgraded. These tests do not send live vehicle commands.

## Source and deployment

- Source repository: `~/psyhitech/ha-fordpass-china/`.
- Installed HA component: `~/homeassistant-config/custom_components/fordpass_cn_modern/`.
- Codec deployment: `~/fordpass-cn-modern/`.

A Git push does not deploy the component. Before deployment, back up the
installed component and private settings outside Git. Stop or unload the
integration as appropriate, copy the tested component, and reload HA. Verify
entity availability and query timestamps through HA's API. Restore the backup
if the updated integration fails to load. Private settings and native vendor
files must not be overwritten from the source checkout.

The old MacBook home-kiosk copy is retained only as historical material;
it must not be used as an upstream source or synchronized over this repository.
