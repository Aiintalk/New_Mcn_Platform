"""Unit tests for qianchuan_review_service（不依赖 DB / AI）。"""
import pytest

from app.services.qianchuan_review_service import (
    ScriptItem,
    ExcelRow,
    merge_scripts_and_excel,
    build_user_message,
)


# ---------- merge_scripts_and_excel ----------

def test_merge_no_excel():
    """无 Excel 时，脚本原样返回，顺序不变。"""
    scripts = [
        ScriptItem(title="脚本A", content="内容A"),
        ScriptItem(title="脚本B", content="内容B"),
    ]
    result = merge_scripts_and_excel(scripts, [])
    assert len(result) == 2
    assert result[0]["title"] == "脚本A"
    assert result[0]["spend"] is None


def test_merge_matches_by_first_12_chars():
    """脚本标题与 Excel video_theme 取前12字模糊匹配。"""
    scripts = [ScriptItem(title="这是一个千川脚本标题内容", content="脚本全文")]
    excel = [ExcelRow(
        video_theme="这是一个千川脚本标题内容完整版",
        spend="1000",
        roi="3.5",
        impressions=None, ctr=None, three_sec_rate=None,
        conversions=None, cost_per_conversion=None,
        cpm=None, time_range=None,
    )]
    result = merge_scripts_and_excel(scripts, excel)
    assert len(result) == 1
    assert result[0]["spend"] == "1000"
    assert result[0]["roi"] == "3.5"


def test_merge_title_replaced_by_excel_video_theme():
    """匹配成功时，title 使用 Excel 的 video_theme。"""
    scripts = [ScriptItem(title="开头相同的内容，脚本标题", content="内容")]
    excel = [ExcelRow(
        video_theme="开头相同的内容，Excel标题",
        spend="500",
        roi=None, impressions=None, ctr=None, three_sec_rate=None,
        conversions=None, cost_per_conversion=None,
        cpm=None, time_range=None,
    )]
    result = merge_scripts_and_excel(scripts, excel)
    assert result[0]["title"] == "开头相同的内容，Excel标题"


def test_merge_unmatched_excel_appended():
    """Excel 中有但脚本无对应的行，追加到列表末尾，content 为空。"""
    scripts = [ScriptItem(title="脚本甲内容", content="全文")]
    excel = [
        ExcelRow(video_theme="脚本甲内容完整名称", spend="800", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
        ExcelRow(video_theme="完全不同的素材名称", spend="200", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
    ]
    result = merge_scripts_and_excel(scripts, excel)
    assert len(result) == 2
    assert result[1]["title"] == "完全不同的素材名称"
    assert result[1]["content"] == ""


def test_merge_sorted_by_spend_descending():
    """按消耗（spend）降序排列。"""
    scripts = [
        ScriptItem(title="低消耗脚本内容", content="内容A"),
        ScriptItem(title="高消耗脚本内容", content="内容B"),
    ]
    excel = [
        ExcelRow(video_theme="低消耗脚本内容", spend="100", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
        ExcelRow(video_theme="高消耗脚本内容", spend="9999", roi=None,
                 impressions=None, ctr=None, three_sec_rate=None,
                 conversions=None, cost_per_conversion=None,
                 cpm=None, time_range=None),
    ]
    result = merge_scripts_and_excel(scripts, excel)
    assert result[0]["spend"] == "9999"
    assert result[1]["spend"] == "100"


def test_merge_no_spend_sorted_last():
    """无消耗数据的条目排在有消耗数据的后面。"""
    scripts = [
        ScriptItem(title="无数据脚本", content="内容C"),
        ScriptItem(title="有数据脚本", content="内容D"),
    ]
    excel = [ExcelRow(video_theme="有数据脚本完整", spend="500", roi=None,
                      impressions=None, ctr=None, three_sec_rate=None,
                      conversions=None, cost_per_conversion=None,
                      cpm=None, time_range=None)]
    result = merge_scripts_and_excel(scripts, excel)
    assert result[0]["title"] == "有数据脚本完整"
    assert result[1]["title"] == "无数据脚本"


# ---------- build_user_message ----------

def test_build_user_message_basic():
    items = [{"title": "脚本一", "content": "文案内容", "spend": None,
              "impressions": None, "ctr": None, "three_sec_rate": None,
              "conversions": None, "cost_per_conversion": None,
              "roi": None, "cpm": None, "time_range": None}]
    msg = build_user_message(items)
    assert "以下是本期千川投放素材（共1条）" in msg
    assert "### 素材 1：脚本一" in msg
    assert "【完整脚本】" in msg
    assert "文案内容" in msg


def test_build_user_message_includes_metrics():
    items = [{"title": "素材X", "content": "内容", "spend": "1234",
              "roi": "3.5", "conversions": "89",
              "impressions": None, "ctr": None, "three_sec_rate": None,
              "cost_per_conversion": None, "cpm": None, "time_range": None}]
    msg = build_user_message(items)
    assert "消耗: 1234元" in msg
    assert "ROI: 3.5" in msg
    assert "转化数: 89" in msg


def test_build_user_message_truncates_at_2000():
    """单条脚本超过 2000 字应截断并注明。"""
    long_content = "千" * 2500
    items = [{"title": "长脚本", "content": long_content, "spend": None,
              "impressions": None, "ctr": None, "three_sec_rate": None,
              "conversions": None, "cost_per_conversion": None,
              "roi": None, "cpm": None, "time_range": None}]
    msg = build_user_message(items)
    assert "...(已截断)" in msg
    script_part = msg.split("【完整脚本】")[1].split("---")[0]
    assert len(script_part) < 2100


def test_build_user_message_multiple_items_separated():
    items = [
        {"title": "素材一", "content": "内容一", "spend": None,
         "impressions": None, "ctr": None, "three_sec_rate": None,
         "conversions": None, "cost_per_conversion": None,
         "roi": None, "cpm": None, "time_range": None},
        {"title": "素材二", "content": "内容二", "spend": None,
         "impressions": None, "ctr": None, "three_sec_rate": None,
         "conversions": None, "cost_per_conversion": None,
         "roi": None, "cpm": None, "time_range": None},
    ]
    msg = build_user_message(items)
    assert "### 素材 1：素材一" in msg
    assert "### 素材 2：素材二" in msg
    assert "---" in msg
