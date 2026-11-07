"""Track B (M4): note loading, rendering, regeneration and the cluster batch."""

import json
from typing import Any
from pathlib import Path
from datetime import date, datetime, timezone

import httpx
import pytest

from deskmate.llm import FakeLLM, ClusterResult
from deskmate.store import note_path, read_note, note_is_stale, write_bookmark, bookmarks_in_period
from deskmate.models import Bookmark, InsightNote, InsightCluster
from deskmate.insight import load_insight, build_insight, render_note_body
from deskmate.periods import Period, resolve_period
from deskmate.settings import DeskmateSettings
from deskmate.summarize.fetch import build_client


TODAY = date(2026, 11, 6)
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
WEBRTC_ID = "7f3a9c2e-5b1d-4e8a-9c3f-2d7e6a1b4c05"
ICE_ID = "a1b2c3d4-0001-4000-8000-000000000001"
RUST_ID = "a1b2c3d4-0002-4000-8000-000000000002"
WEBRTC_LINK = "[[2026-11-03 WebRTC 재접속 처리 패턴 7f3a9c]]"
RUST_LINK = "[[2026-11-05 Rust async await 입문 1부 Future란 정리 a1b2c3]]"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never wait for the call interval in tests."""
    monkeypatch.setattr("deskmate.summarize.runner._sleep", lambda seconds: None)


@pytest.fixture
def offline_client() -> httpx.Client:
    """HTTP client whose every request fails (the fixture repo must not need the network)."""
    return build_client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))


@pytest.fixture
def period() -> Period:
    """Return the fixture note's period."""
    return resolve_period(today=TODAY)


def test_load_insight_returns_fixture_note(settings: DeskmateSettings, period: Period) -> None:
    """The sample note loads with its clusters and rendered body; a missing period is ``None``."""
    loaded = load_insight(settings, "Default", period)
    assert loaded is not None
    note, rendered = loaded
    assert note.path == note_path(settings, "Default", period)
    assert [cluster.topic for cluster in note.clusters] == ["WebRTC 재접속", "Rust 비동기"]
    assert rendered.startswith("# 위클리 인사이트 (2026-10-31 ~ 2026-11-06)")
    assert (
        load_insight(settings, "Default", resolve_period(since="2025-01-01", until="2025-01-07", today=TODAY)) is None
    )
    assert load_insight(settings, "Profile 1", period) is None


def test_render_matches_fixture_layout(settings: DeskmateSettings, period: Period) -> None:
    """Rendering the fixture's front matter reproduces the fixture body exactly."""
    note, rendered = read_note(note_path(settings, "Default", period))
    bookmarks = bookmarks_in_period(settings, "Default", period)
    assert render_note_body(note, bookmarks) == rendered + "\n"


def test_render_edge_cases() -> None:
    """Unknown ids degrade to ``(id)``, LLM text is flattened, empty unavailable omits its section."""
    note = InsightNote(
        profile="Default",
        since=date(2026, 11, 1),
        until=date(2026, 11, 7),
        generated_at="2026-11-07T00:00:00Z",
        clusters=[
            InsightCluster(
                topic="주제\n## 가짜 제목",
                bookmark_ids=["unknown-id"],
                summary="첫 줄\n둘째 줄",
                correlation="관계",
                question="질문?",
            )
        ],
    )
    body = render_note_body(note, [])
    assert body == (
        "# 위클리 인사이트 (2026-11-01 ~ 2026-11-07)\n\n## 주제 ## 가짜 제목\n첫 줄 둘째 줄\n\n- (unknown-id)\n\n"
        "**관계**: 관계\n\n**질문**: 질문?\n"
    )
    assert "## 본문 미확보" not in body
    assert render_note_body(InsightNote("Default", date(2026, 11, 1), date(2026, 11, 7), ""), []) == (
        "# 위클리 인사이트 (2026-11-01 ~ 2026-11-07)\n"
    )


def test_build_insight_empty_period_writes_nothing(settings: DeskmateSettings, offline_client: httpx.Client) -> None:
    """A period without bookmarks returns an empty note and leaves the disk untouched."""
    llm = FakeLLM()
    period = resolve_period(since="2025-01-01", until="2025-01-07", today=TODAY)
    note = build_insight(settings, llm, "Default", period, now=NOW, client=offline_client)
    assert note.path is None and note.clusters == [] and note.bookmark_ids == []
    assert note.profile == "Default" and note.since == date(2025, 1, 1)
    assert not note_path(settings, "Default", period).exists()
    assert llm.calls == []
    assert not settings.resolved_usage_log.exists()


def test_build_insight_regenerates_note_and_keeps_conversations(
    settings: DeskmateSettings, fake_llm_responses: dict[str, Any], period: Period, offline_client: httpx.Client
) -> None:
    """Rebuilding the fixture week rewrites the note from the canned clusters and keeps ``## 대화 기록``."""
    llm = FakeLLM(fake_llm_responses)
    note = build_insight(settings, llm, "Default", period, now=NOW, client=offline_client)
    path = note_path(settings, "Default", period)
    assert note.path == path and path.is_file()
    assert note.generated_at == "2026-11-06T12:00:00Z" and note.complete is True

    reloaded, rendered = read_note(path)
    canned = fake_llm_responses["clusters"]["clusters"]
    assert [cluster.to_dict() for cluster in reloaded.clusters] == canned
    assert reloaded.bookmark_ids == [WEBRTC_ID, ICE_ID, RUST_ID]
    assert reloaded.unavailable == [RUST_ID]
    assert len(reloaded.conversations) == 1
    assert reloaded.conversations[0].startswith("## 대화 기록 (2026-11-06 10:12)")
    assert "ICE restart 2단계 전략" in reloaded.conversations[0]

    assert f"- {WEBRTC_LINK}" in rendered
    assert rendered.endswith(f"## 본문 미확보\n- {RUST_LINK}")
    assert rendered.count("## 본문 미확보") == 1
    assert "**질문**: 아바타 통화에서" in rendered

    current = bookmarks_in_period(settings, "Default", period)
    assert note_is_stale(reloaded, current) is False
    assert [call["op"] for call in llm.calls] == ["cluster"]  # the ok bookmarks are cached; Rust is in back-off
    assert llm.calls[0]["ids"] == [WEBRTC_ID, ICE_ID, RUST_ID]

    lines = [json.loads(line) for line in settings.resolved_usage_log.read_text(encoding="utf-8").splitlines()]
    assert [line["op"] for line in lines] == ["cluster"]
    assert lines[0]["profile"] == "Default" and "bookmark_id" not in lines[0]


def test_build_insight_drops_unknown_cluster_ids(
    settings: DeskmateSettings, period: Period, offline_client: httpx.Client
) -> None:
    """Ids the model invented are removed; clusters left empty disappear."""

    class InventingLLM(FakeLLM):
        """Model that returns ids outside the period."""

        def cluster(self, items: Any) -> ClusterResult:
            self.calls.append({"op": "cluster"})
            return ClusterResult(
                clusters=[
                    InsightCluster("진짜", [WEBRTC_ID, "made-up", ICE_ID], "s", "c", "q?"),
                    InsightCluster("가짜", ["made-up-2"], "s", "c", "q?"),
                ]
            )

    note = build_insight(settings, InventingLLM(), "Default", period, now=NOW, client=offline_client)
    assert [cluster.topic for cluster in note.clusters] == ["진짜"]
    assert note.clusters[0].bookmark_ids == [WEBRTC_ID, ICE_ID]
    _, rendered = read_note(Path(note.path))
    assert "made-up" not in rendered and "(made-up)" not in rendered


def test_build_insight_summarizes_pending_bookmarks_first(
    settings: DeskmateSettings, fake_llm_responses: dict[str, Any], period: Period, tmp_path: Path
) -> None:
    """A pending bookmark in the period is fetched and summarized before clustering."""
    page = (
        "<html><head><meta charset='utf-8'><title>CSS Grid</title></head><body><article><h1>CSS Grid 치트시트</h1>"
        + "".join(
            f"<p>grid-template-columns, grid-area, gap 같은 CSS Grid 속성과 레이아웃 패턴을 정리한 표 {i}.</p>"
            for i in range(8)
        )
        + "</article></body></html>"
    )
    client = build_client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "text/html"}, content=page.encode())
        )
    )
    guid = "c55c0000-0003-4000-8000-000000000003"
    pending = Bookmark(
        title="CSS Grid 치트시트",
        url="https://example.com/css/grid-cheatsheet",
        guid=guid,
        profile="Default",
        date=date(2026, 11, 6),
        tags=["개발", "CSS"],
    )
    write_bookmark(
        pending, settings.profile_bookmarks_dir("Default") / "2026" / f"2026-11-06 CSS Grid 치트시트 {guid[:6]}.md"
    )

    llm = FakeLLM(fake_llm_responses)
    note = build_insight(settings, llm, "Default", period, now=NOW, client=client)
    assert guid in note.bookmark_ids and guid not in note.unavailable
    assert [call["op"] for call in llm.calls] == ["summarize", "cluster"]
    summarized = next(b for b in bookmarks_in_period(settings, "Default", period) if b.guid == guid)
    assert summarized.summary_status == "ok" and "CSS Grid" in summarized.body
    lines = [json.loads(line) for line in settings.resolved_usage_log.read_text(encoding="utf-8").splitlines()]
    assert [line["op"] for line in lines] == ["summarize", "cluster"]


# --- model outage: previous note as fallback -----------------------------------------------


class _BusyLLM(FakeLLM):
    """Model whose cluster call is unavailable (503 / timeout)."""

    def cluster(self, items: list[Any]) -> ClusterResult:
        raise RuntimeError("503 UNAVAILABLE: high demand")


def _write_pending(settings: DeskmateSettings, title: str, guid: str, day: date) -> Bookmark:
    bookmark = Bookmark(title=title, url=f"https://example.com/{guid[:6]}", guid=guid, profile="Default", date=day)
    target = settings.profile_bookmarks_dir("Default") / str(day.year) / f"{day.isoformat()} {title} {guid[:6]}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_bookmark(bookmark, target)
    return bookmark


def test_build_insight_serves_previous_note_when_cluster_model_is_down(
    settings: DeskmateSettings, period: Period, offline_client: httpx.Client
) -> None:
    """Cluster failure + existing note → the old note comes back degraded, untouched on disk, with the new titles."""
    path = note_path(settings, "Default", period)
    before = path.read_text(encoding="utf-8")
    _write_pending(settings, "새 글", "deadbeef-0000-4000-8000-000000000001", date(2026, 11, 6))

    note = build_insight(settings, _BusyLLM(), "Default", period, now=NOW, client=offline_client)

    assert note.degraded is True and note.pending_titles == ["새 글"]
    assert note.path == path and path.read_text(encoding="utf-8") == before
    assert len(note.clusters) == 2 and note.bookmark_ids == [WEBRTC_ID, ICE_ID, RUST_ID]


def test_build_insight_without_previous_note_raises_when_model_is_down(
    settings: DeskmateSettings, offline_client: httpx.Client
) -> None:
    """No note to fall back on → ClusterUnavailableError (the tool turns it into a friendly error)."""
    from deskmate.insight import ClusterUnavailableError

    period = Period(since=date(2026, 10, 1), until=date(2026, 10, 7))
    _write_pending(settings, "시월 글", "deadbeef-0000-4000-8000-000000000002", date(2026, 10, 3))
    with pytest.raises(ClusterUnavailableError):
        build_insight(settings, _BusyLLM(), "Default", period, now=NOW, client=offline_client)
    assert not note_path(settings, "Default", period).exists()
