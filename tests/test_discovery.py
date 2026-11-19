"""Campaign discovery filters, classification and the seen-campaign file.

The seen file is what keeps a scheduled scan from re-reporting the same
campaigns, so load and save have to agree on one path — they did not.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from web3_agent_kit.airdrop.discovery import (
    CampaignCategory,
    CampaignDiscovery,
    CampaignStatus,
    DiscoveredCampaign,
    DiscoveryConfig,
)


def _campaign(**kwargs) -> DiscoveredCampaign:
    base = {
        "platform": "galxe",
        "campaign_id": "c1",
        "title": "Campaign",
        "url": "https://example.com/c1",
    }
    base.update(kwargs)
    return DiscoveredCampaign(**base)


class TestCampaignProperties:
    def test_reward_makes_it_high_value(self):
        assert _campaign(points=0, reward_amount="10 USDC").is_high_value is True

    def test_a_hundred_points_is_high_value(self):
        assert _campaign(points=100).is_high_value is True

    def test_low_points_without_reward_is_not(self):
        assert _campaign(points=99).is_high_value is False

    def test_no_end_time_is_not_ending_soon(self):
        assert _campaign().is_ending_soon is False

    def test_ending_in_an_hour_is_ending_soon(self):
        soon = datetime.now(timezone.utc) + timedelta(hours=1)
        assert _campaign(end_time=soon).is_ending_soon is True

    def test_ending_in_two_days_is_not_ending_soon(self):
        later = datetime.now(timezone.utc) + timedelta(days=2)
        assert _campaign(end_time=later).is_ending_soon is False

    def test_an_already_ended_campaign_is_not_ending_soon(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _campaign(end_time=past).is_ending_soon is False

    def test_description_is_truncated_in_the_dict(self):
        assert len(_campaign(description="x" * 500).to_dict()["description"]) == 200


class TestFilters:
    def _discovery(self, **kwargs) -> CampaignDiscovery:
        return CampaignDiscovery(DiscoveryConfig(**kwargs))

    def test_min_points_drops_low_ones(self):
        kept = self._discovery(min_points=50)._filter_campaigns(
            [_campaign(points=10), _campaign(points=60)]
        )
        assert [c.points for c in kept] == [60]

    def test_active_only_drops_ended(self):
        kept = self._discovery(active_only=True)._filter_campaigns(
            [_campaign(status=CampaignStatus.ENDED), _campaign(campaign_id="c2")]
        )
        assert [c.campaign_id for c in kept] == ["c2"]

    def test_category_filter(self):
        kept = self._discovery(categories=["defi"])._filter_campaigns(
            [
                _campaign(category=CampaignCategory.DEFI),
                _campaign(campaign_id="c2", category=CampaignCategory.NFT),
            ]
        )
        assert [c.campaign_id for c in kept] == ["c1"]

    def test_chain_filter(self):
        kept = self._discovery(chains=["ethereum"])._filter_campaigns(
            [_campaign(chain="solana"), _campaign(campaign_id="c2", chain="ethereum")]
        )
        assert [c.campaign_id for c in kept] == ["c2"]

    def test_a_campaign_without_a_chain_survives_the_chain_filter(self):
        kept = self._discovery(chains=["ethereum"])._filter_campaigns([_campaign(chain="")])
        assert len(kept) == 1

    def test_no_filters_keeps_everything(self):
        assert len(self._discovery()._filter_campaigns([_campaign()])) == 1


class TestSeenFile:
    def test_save_then_load_round_trips(self, tmp_path):
        path = str(tmp_path / "seen.json")
        first = CampaignDiscovery(DiscoveryConfig(save_path=path))
        first._save_seen([_campaign()])
        assert json.loads((tmp_path / "seen.json").read_text())["count"] == 1

        second = CampaignDiscovery(DiscoveryConfig(save_path=path))
        second._load_seen()
        assert "galxe:c1" in second._seen_campaigns

    def test_only_a_save_path_is_enough_to_dedupe_across_runs(self, tmp_path):
        # seen_path and save_path used to be separate fields: a user who set
        # only the save path wrote the file and never read it back.
        path = str(tmp_path / "seen.json")
        CampaignDiscovery(DiscoveryConfig(save_path=path))._save_seen([_campaign()])
        reloaded = CampaignDiscovery(DiscoveryConfig(save_path=path))
        reloaded._load_seen()
        assert reloaded._campaign_key(_campaign()) in reloaded._seen_campaigns

    def test_an_explicit_seen_path_wins(self, tmp_path):
        seen = tmp_path / "seen.json"
        seen.write_text(json.dumps({"seen": ["galxe:explicit"]}))
        discovery = CampaignDiscovery(
            DiscoveryConfig(seen_path=str(seen), save_path=str(tmp_path / "other.json"))
        )
        discovery._load_seen()
        assert discovery._seen_campaigns == {"galxe:explicit"}

    def test_without_paths_nothing_happens(self):
        discovery = CampaignDiscovery(DiscoveryConfig())
        discovery._load_seen()
        discovery._save_seen([_campaign()])
        assert discovery._seen_campaigns == {"galxe:c1"}

    def test_a_corrupt_file_is_ignored(self, tmp_path):
        path = tmp_path / "seen.json"
        path.write_text("{not json")
        discovery = CampaignDiscovery(DiscoveryConfig(seen_path=str(path)))
        discovery._load_seen()
        assert discovery._seen_campaigns == set()

    def test_an_unwritable_path_does_not_raise(self, tmp_path):
        discovery = CampaignDiscovery(DiscoveryConfig(save_path=str(tmp_path / "x" / "y.json")))
        discovery._save_seen([_campaign()])
        assert (tmp_path / "x" / "y.json").exists()


class TestPlatformDispatch:
    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            CampaignDiscovery(DiscoveryConfig()).discover_platform("nope")

    def test_known_platform_reaches_its_scanner(self, monkeypatch):
        discovery = CampaignDiscovery(DiscoveryConfig())
        monkeypatch.setattr(CampaignDiscovery, "_scan_zealy", lambda self: [_campaign()])
        assert len(discovery.discover_platform("zealy")) == 1


class TestExport:
    def test_urls_are_extracted(self):
        discovery = CampaignDiscovery(DiscoveryConfig())
        assert discovery.export_urls([_campaign()]) == ["https://example.com/c1"]


class TestGalxeParse:
    def _discovery(self) -> CampaignDiscovery:
        return CampaignDiscovery(DiscoveryConfig())

    def test_a_node_is_parsed(self):
        node = {
            "id": "c9",
            "name": "Quest",
            "description": "d",
            "tasks": [{}, {}],
            "space": {"name": "space"},
        }
        campaign = self._discovery()._parse_galxe_campaign(node)
        assert campaign.campaign_id == "c9"
        assert campaign.points == 20
        assert campaign.task_count == 2
        assert campaign.space_name == "space"
        assert campaign.url == "https://app.galxe.com/quest/c9"

    def test_a_missing_id_is_rejected(self):
        assert self._discovery()._parse_galxe_campaign({}) is None

    def test_an_id_of_none_is_rejected_not_stringified(self):
        assert self._discovery()._parse_galxe_campaign({"id": None}) is None

    def test_a_past_end_time_marks_it_ended(self):
        past = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
        campaign = self._discovery()._parse_galxe_campaign({"id": "c", "endTime": past})
        assert campaign.status is CampaignStatus.ENDED

    def test_an_imminent_end_time_marks_it_ending_soon(self):
        soon = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        campaign = self._discovery()._parse_galxe_campaign({"id": "c", "endTime": soon})
        assert campaign.status is CampaignStatus.ENDING_SOON

    def test_a_bad_timestamp_leaves_the_time_empty(self):
        campaign = self._discovery()._parse_galxe_campaign({"id": "c", "endTime": "not-a-time"})
        assert campaign.end_time is None
        assert campaign.status is CampaignStatus.ACTIVE


class TestGalxeScan:
    def _resp(self, payload):
        return type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: payload})()

    def test_a_page_of_campaigns_is_returned(self, monkeypatch):
        discovery = CampaignDiscovery(DiscoveryConfig())
        payload = {
            "data": {
                "campaignList": {
                    "edges": [{"node": {"id": "a", "name": "A", "tasks": []}}],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        }
        monkeypatch.setattr(discovery.session, "post", lambda *a, **k: self._resp(payload))
        assert [c.campaign_id for c in discovery._scan_galxe()] == ["a"]

    def test_pagination_follows_the_cursor(self):
        discovery = CampaignDiscovery(DiscoveryConfig())
        seen_variables = []

        def post(url, json=None, timeout=None):
            seen_variables.append(json["variables"])
            page = len(seen_variables)
            return self._resp(
                {
                    "data": {
                        "campaignList": {
                            "edges": [{"node": {"id": f"c{page}", "tasks": []}}],
                            "pageInfo": {
                                "hasNextPage": page == 1,
                                "endCursor": f"cursor{page}",
                            },
                        }
                    }
                }
            )

        discovery.session.post = post
        campaigns = discovery._scan_galxe()
        assert [c.campaign_id for c in campaigns] == ["c1", "c2"]
        assert seen_variables[1]["after"] == "cursor1"

    def test_a_scan_error_stops_and_keeps_what_was_found(self):
        discovery = CampaignDiscovery(DiscoveryConfig())

        def post(*a, **k):
            raise RuntimeError("boom")

        discovery.session.post = post
        assert discovery._scan_galxe() == []


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _scan(discovery, monkeypatch, payload, status=200):
    monkeypatch.setattr(discovery.session, "get", lambda *a, **k: _Resp(payload, status))
    return discovery


class TestScanners:
    """All seven scanners share one builder; a bad entry must not poison it."""

    @pytest.mark.parametrize(
        ("platform", "payload"),
        [
            ("zealy", [{"slug": "s1", "name": "Community", "memberCount": "5"}]),
            ("layer3", {"data": [{"id": "q1", "title": "Q", "xp": "9"}]}),
            ("questn", {"data": {"list": [{"id": 1, "title": "Q", "points": None}]}}),
            ("taskon", {"data": {"list": [{"id": 2, "title": "Q"}]}}),
            ("intract", {"data": [{"id": "i1", "title": "Q", "participants": "3"}]}),
            ("port3", {"data": [{"id": "p1", "title": "Q", "points": ""}]}),
        ],
    )
    def test_a_scan_returns_a_campaign(self, platform, payload, monkeypatch):
        discovery = _scan(CampaignDiscovery(DiscoveryConfig()), monkeypatch, payload)
        campaigns = discovery.discover_platform(platform)
        assert len(campaigns) == 1
        assert campaigns[0].platform == platform

    @pytest.mark.parametrize(
        ("platform", "payload"),
        [
            ("zealy", [{"name": "no slug"}, {"slug": "ok"}]),
            ("layer3", {"data": [{"title": "no id"}, {"id": "ok"}]}),
            ("port3", {"data": [{"id": None}, {"id": "ok"}]}),
        ],
    )
    def test_an_entry_without_an_id_is_skipped(self, platform, payload, monkeypatch):
        discovery = _scan(CampaignDiscovery(DiscoveryConfig()), monkeypatch, payload)
        assert [c.campaign_id for c in discovery.discover_platform(platform)] == ["ok"]

    def test_string_points_do_not_break_the_filters(self, monkeypatch):
        # A string "50" compared against an int threshold raises TypeError.
        discovery = DiscoveryConfig(min_points=10)
        discovery = _scan(CampaignDiscovery(discovery), monkeypatch, [{"id": "a", "points": "50"}])
        assert len(discovery.discover_platform("port3")) == 1

    def test_non_200_is_empty(self, monkeypatch):
        discovery = _scan(CampaignDiscovery(DiscoveryConfig()), monkeypatch, {}, status=503)
        assert discovery.discover_platform("questn") == []

    def test_a_null_title_becomes_untitled(self, monkeypatch):
        discovery = _scan(CampaignDiscovery(DiscoveryConfig()), monkeypatch, [{"id": "a"}])
        assert discovery.discover_platform("port3")[0].title == "Untitled"

    def test_tags_null_becomes_a_list(self, monkeypatch):
        discovery = _scan(
            CampaignDiscovery(DiscoveryConfig()), monkeypatch, [{"id": "a", "tags": None}]
        )
        assert discovery.discover_platform("intract")[0].tags == []
