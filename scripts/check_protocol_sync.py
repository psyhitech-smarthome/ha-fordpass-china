"""Check the standalone and bundled HA protocol sources are identical."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
for name in ("client.py", "signing.py"):
    standalone = (root / "fordpass_china_next" / name).read_bytes()
    bundled = (root / "custom_components/fordpass_cn_modern/protocol" / name).read_bytes()
    if standalone != bundled:
        raise SystemExit(f"Protocol copies differ: {name}")
print("Protocol sources match")
