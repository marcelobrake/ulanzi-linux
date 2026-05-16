import yaml
import json
import zipfile
import io
import os
from ulanzi_linux.domain.button_config import DeckConfig, ButtonConfig
from ulanzi_linux.application.artifacts import build_default_page_bundle

config_path = os.path.expanduser("~/.config/ulanzi/deck.yaml")
with open(config_path, "r") as f:
    cfg_dict = yaml.safe_load(f)

# Convert nested dicts to objects if necessary, though DeckConfig.from_dict is preferred if it exists.
# Based on the error, DeckConfig expects objects or the raw dict structure is not being parsed correctly for dataclasses.
# Let's try to use a proper loader if available or manually map.
# Since I don't know the exact from_dict method, I'll attempt a manual conversion for common fields.

fixed = [ButtonConfig(**b) for b in cfg_dict.get('fixed_buttons', [])]
pages = {int(k): [ButtonConfig(**b) for b in v] for k, v in cfg_dict.get('pages', {}).items()}
cfg = DeckConfig(fixed_buttons=fixed, pages=pages)

zip_data = build_default_page_bundle(cfg)
with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
    with z.open("manifest.json") as f:
        manifest = json.load(f)

keys = ["0_0", "1_0", "2_0", "0_2", "1_2", "2_2"]
for key in keys:
    print(f"{key}: {manifest.get(key)}")
