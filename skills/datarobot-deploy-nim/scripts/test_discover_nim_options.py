# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from discover_nim_options import filter_gpu_bundles, pick_nim_template


class _B:
    def __init__(
        self,
        id: str,
        has_gpu: bool,
        gpu_count: int = 0,
        gpu_memory_bytes: int = 0,
    ) -> None:
        self.id, self.name = id, id
        self.has_gpu = has_gpu
        self.gpu_count = gpu_count
        self.gpu_memory_bytes = gpu_memory_bytes


def test_filters_non_gpu_and_sorts() -> None:
    out = filter_gpu_bundles(
        [
            _B("cpu", False),
            _B("g2", True, 2, 10),
            _B("g1a", True, 1, 80),
            _B("g1b", True, 1, 40),
        ]
    )
    assert [b.id for b in out] == ["g1b", "g1a", "g2"]


def test_pick_template_by_substring() -> None:
    tpls = [{"id": "t1", "name": "Llama 3 NIM"}, {"id": "t2", "name": "Mixtral NIM"}]
    chosen = pick_nim_template(tpls, "mixtral")
    assert chosen is not None and chosen["id"] == "t2"


def test_pick_template_defaults_to_first() -> None:
    tpls = [{"id": "t1", "name": "A"}, {"id": "t2", "name": "B"}]
    chosen = pick_nim_template(tpls)
    assert chosen is not None and chosen["id"] == "t1"


def test_pick_template_empty_returns_none() -> None:
    assert pick_nim_template([], "x") is None


def test_pick_template_no_match_returns_none() -> None:
    assert pick_nim_template([{"id": "t1", "name": "A"}], "zzz") is None
