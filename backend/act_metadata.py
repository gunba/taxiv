from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set

CONFIG_ENV_VAR = "TAXIV_DATASETS_CONFIG"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "datasets.json"


@dataclass(frozen=True)
class ActExclusions:
    ref_ids: Set[str] = field(default_factory=set)

    @property
    def internal_ids(self) -> Set[str]:
        return {ref.replace(":", "_").replace("/", "_") for ref in self.ref_ids}


@dataclass(frozen=True)
class ActMetadata:
    id: str
    title: str
    description: str
    is_default: bool = False
    exclusions: ActExclusions = field(default_factory=ActExclusions)
    tokenizer_prefixes: Set[str] = field(default_factory=set)
    tokenizer_supports_section_gaps: bool = True


@dataclass(frozen=True)
class DatasetMetadata:
    id: str
    title: str
    type: str
    description: str


@dataclass(frozen=True)
class MetadataBundle:
    default_act_id: str
    acts: Dict[str, ActMetadata]
    datasets: Dict[str, DatasetMetadata]


def _resolve_config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_CONFIG_PATH


def _load_raw_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Dataset config not found at {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_bundle(raw: dict) -> MetadataBundle:
    default_act = raw.get("default_act")
    acts_map: Dict[str, ActMetadata] = {}
    datasets_map: Dict[str, DatasetMetadata] = {}
    for entry in raw.get("acts", []):
        act_id = entry.get("id")
        if not act_id:
            continue
        exclusions = ActExclusions(ref_ids=set(entry.get("exclusions", {}).get("ref_ids", [])))
        tokenizer_cfg = entry.get("tokenizer", {})
        metadata = ActMetadata(
            id=act_id,
            title=entry.get("title", act_id),
            description=entry.get("description", ""),
            is_default=(act_id == default_act),
            exclusions=exclusions,
            tokenizer_prefixes=set(tokenizer_cfg.get("explicit_prefixes", [])),
            tokenizer_supports_section_gaps=bool(tokenizer_cfg.get("supports_section_gaps", True)),
        )
        acts_map[act_id] = metadata
    for entry in raw.get("datasets", []):
        dataset_id = entry.get("id")
        if not dataset_id:
            continue
        datasets_map[dataset_id] = DatasetMetadata(
            id=dataset_id,
            title=entry.get("title", dataset_id),
            type=entry.get("type", "document"),
            description=entry.get("description", ""),
        )
    if not default_act and acts_map:
        default_act = next(iter(acts_map))
    return MetadataBundle(default_act_id=default_act or "", acts=acts_map, datasets=datasets_map)


@lru_cache(maxsize=8)
def _get_metadata_bundle_cached(config_path_str: str, version_token: float) -> MetadataBundle:
    config_path = Path(config_path_str)
    raw = _load_raw_config(config_path)
    return _parse_bundle(raw)


def get_metadata_bundle() -> MetadataBundle:
    config_path = _resolve_config_path()
    try:
        version_token = config_path.stat().st_mtime
    except FileNotFoundError:
        # Let _load_raw_config raise the detailed error shortly after.
        version_token = 0.0
    return _get_metadata_bundle_cached(str(config_path), version_token)


def get_default_act_id() -> str:
    bundle = get_metadata_bundle()
    return bundle.default_act_id or next(iter(bundle.acts.keys()), "")


def get_act_metadata(act_id: Optional[str]) -> Optional[ActMetadata]:
    if not act_id:
        return get_metadata_bundle().acts.get(get_default_act_id())
    return get_metadata_bundle().acts.get(act_id)


def list_acts() -> List[ActMetadata]:
    return list(get_metadata_bundle().acts.values())


def list_datasets() -> List[DatasetMetadata]:
    return list(get_metadata_bundle().datasets.values())


def ensure_valid_act_id(act_id: Optional[str]) -> str:
    metadata = get_act_metadata(act_id)
    if not metadata:
        raise ValueError(f"Unknown act id '{act_id}'")
    return metadata.id
