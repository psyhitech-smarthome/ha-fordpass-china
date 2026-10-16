# Maintainer workflow

Development, testing and GitHub operations take place on the home Mac mini.
The laptop is only the SSH client.

```sh
ssh mac-1
cd ~/psyhitech/ha-fordpass-china
git status --short --branch
```

Create a dedicated development environment (separate from the running HA):

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -e . homeassistant==2026.10.1
```

Run the checks with that environment:

```sh
.venv/bin/python scripts/check_protocol_sync.py
.venv/bin/python -m unittest discover -s tests -v
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

The MacBook source copy has been migrated off the laptop. Essential setup inputs and optional capture tools live in a separate private
lab directory on mac-1, outside this public repository. Generated reverse-
engineering outputs and obsolete caches are discarded, not archived. Never
copy private setup files into Git.
