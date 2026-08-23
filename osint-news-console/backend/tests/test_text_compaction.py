import asyncio

from app.ai_processor import MockProvider, compact_source_text


def test_compaction_keeps_title_and_complete_chinese_sentences():
    title = "央行在北京发布公开市场操作公告"
    body = "公告于今日上午发布。相关操作将在本周内实施。" + "补充信息。" * 100

    result = compact_source_text(title, body, limit=80)

    assert result.startswith(title)
    assert len(result) <= 80
    assert result.endswith("…")


def test_compaction_keeps_foreign_text_without_fake_translation():
    title = "Central bank releases a policy notice"
    body = "The notice was released in London on Tuesday. It takes effect next week."

    result = compact_source_text(title, body, limit=90)

    assert "待中文翻译" not in result
    assert "Central bank" in result
    assert len(result) <= 90


def test_default_provider_marks_foreign_copy_as_original():
    result = asyncio.run(
        MockProvider().process(
            "Agency releases security notice",
            "Official source",
            "The agency released the notice in Washington on Monday.",
        )
    )

    assert "保留原文" in result["tags"]
    assert "待中文翻译" not in result["summary"]
