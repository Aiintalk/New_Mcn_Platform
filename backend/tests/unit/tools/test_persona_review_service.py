"""单元测试：persona_review service 核心函数。"""
import pytest
from app.tools.persona_review.service import (
    merge_scripts_and_excel,
    build_user_message,
    detect_has_excel,
)


# ---------- merge_scripts_and_excel ----------

class TestMergeScriptsAndExcel:
    def test_no_excel_returns_scripts_only(self):
        scripts = [{"title": "视频一", "content": "脚本内容一"}]
        result = merge_scripts_and_excel(scripts, [])
        assert len(result) == 1
        assert result[0]["title"] == "视频一"
        assert result[0]["content"] == "脚本内容一"
        assert result[0].get("likes") is None

    def test_matched_by_video_theme(self):
        scripts = [{"title": "减肥日记第一天", "content": "今天开始减肥..."}]
        excel = [{"video_theme": "减肥日记第一天", "likes": "5000", "completion_rate": "45%"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert len(result) == 1
        assert result[0]["likes"] == "5000"
        assert result[0]["completion_rate"] == "45%"

    def test_title_replaced_by_video_theme_on_match(self):
        """匹配时 title 使用 Excel 的 video_theme（脚本/Excel 前6字相同才能匹配）"""
        scripts = [{"title": "减肥日记第一天", "content": "内容"}]
        excel = [{"video_theme": "减肥日记第一天完整版", "likes": "1000"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert result[0]["title"] == "减肥日记第一天完整版"

    def test_no_match_keeps_script_title(self):
        scripts = [{"title": "完全不同的主题", "content": "内容"}]
        excel = [{"video_theme": "另一个主题完全不同", "likes": "1000"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert result[0]["title"] == "完全不同的主题"

    def test_unmatched_excel_rows_appended(self):
        """未匹配的 Excel 行（有 video_theme 的）追加到末尾，content=""（Q7 确认）"""
        scripts = [{"title": "视频A", "content": "内容A"}]
        excel = [
            {"video_theme": "视频A", "likes": "1000"},
            {"video_theme": "视频B无对应脚本", "likes": "2000"},
        ]
        result = merge_scripts_and_excel(scripts, excel)
        assert len(result) == 2
        unmatched = next(r for r in result if r["title"] == "视频B无对应脚本")
        assert unmatched["content"] == ""
        assert unmatched["likes"] == "2000"

    def test_unmatched_excel_without_video_theme_not_appended(self):
        """无 video_theme 的 Excel 行不追加"""
        scripts = [{"title": "视频A", "content": "内容A"}]
        excel = [{"date": "2026-06-01", "likes": "500"}]  # 无 video_theme
        result = merge_scripts_and_excel(scripts, excel)
        assert len(result) == 1

    def test_sorted_by_likes_desc(self):
        """按点赞数降序排列"""
        scripts = [
            {"title": "低点赞视频", "content": "内容"},
            {"title": "高点赞视频", "content": "内容"},
        ]
        excel = [
            {"video_theme": "低点赞视频", "likes": "100"},
            {"video_theme": "高点赞视频", "likes": "9900"},
        ]
        result = merge_scripts_and_excel(scripts, excel)
        assert int(result[0].get("likes", "0")) > int(result[1].get("likes", "0"))

    def test_no_likes_sorted_last(self):
        scripts = [
            {"title": "无点赞", "content": "内容"},
            {"title": "有点赞", "content": "内容"},
        ]
        excel = [{"video_theme": "有点赞", "likes": "500"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert result[0]["title"] == "有点赞"

    def test_excel_cleaning_no_hash_at(self):
        """Excel 侧清洗不含 #@，脚本侧有 #@"""
        scripts = [{"title": "#减肥日记@博主", "content": "内容"}]
        excel = [{"video_theme": "减肥日记博主", "likes": "1000"}]
        result = merge_scripts_and_excel(scripts, excel)
        # 脚本侧清洗去掉 #@，Excel 侧清洗无 #@，两边都是 "减肥日记博主" 的前12字
        assert result[0]["likes"] == "1000"

    def test_empty_scripts_returns_unmatched_excel(self):
        """无脚本时，有 video_theme 的 Excel 行都追加"""
        excel = [
            {"video_theme": "视频X", "likes": "100"},
            {"video_theme": "视频Y", "likes": "200"},
        ]
        result = merge_scripts_and_excel([], excel)
        assert len(result) == 2

    def test_multiple_scripts_multiple_excel(self):
        scripts = [
            {"title": "视频一", "content": "内容一"},
            {"title": "视频二", "content": "内容二"},
        ]
        excel = [
            {"video_theme": "视频一", "likes": "300"},
            {"video_theme": "视频二", "likes": "100"},
        ]
        result = merge_scripts_and_excel(scripts, excel)
        assert len(result) == 2
        assert result[0]["likes"] == "300"

    def test_all_excel_fields_populated(self):
        scripts = [{"title": "测试视频", "content": "内容"}]
        excel = [{
            "video_theme": "测试视频",
            "date": "2026-06-01",
            "live_theme": "周一场",
            "video_type": "口播",
            "total_plays": "50",
            "completion_rate": "40%",
            "five_sec_rate": "60%",
            "likes": "2000",
            "comments": "150",
            "ad_spend": "500",
        }]
        result = merge_scripts_and_excel(scripts, excel)
        item = result[0]
        assert item["date"] == "2026-06-01"
        assert item["live_theme"] == "周一场"
        assert item["video_type"] == "口播"
        assert item["total_plays"] == "50"
        assert item["completion_rate"] == "40%"
        assert item["five_sec_rate"] == "60%"
        assert item["likes"] == "2000"
        assert item["comments"] == "150"
        assert item["ad_spend"] == "500"


# ---------- detect_has_excel ----------

class TestDetectHasExcel:
    def test_no_excel_fields_returns_false(self):
        merged = [{"title": "视频", "content": "内容"}]
        assert detect_has_excel(merged) is False

    def test_has_likes_returns_true(self):
        merged = [{"title": "视频", "content": "内容", "likes": "1000"}]
        assert detect_has_excel(merged) is True

    def test_has_completion_rate_returns_true(self):
        merged = [{"title": "视频", "content": "内容", "completion_rate": "45%"}]
        assert detect_has_excel(merged) is True

    def test_has_ad_spend_returns_true(self):
        merged = [{"title": "视频", "content": "内容", "ad_spend": "500"}]
        assert detect_has_excel(merged) is True

    def test_empty_string_fields_returns_false(self):
        merged = [{"title": "视频", "likes": "", "ad_spend": ""}]
        assert detect_has_excel(merged) is False

    def test_multiple_items_any_match(self):
        merged = [
            {"title": "视频A", "content": "内容"},
            {"title": "视频B", "content": "", "likes": "500"},
        ]
        assert detect_has_excel(merged) is True


# ---------- build_user_message ----------

class TestBuildUserMessage:
    def test_basic_structure(self):
        merged = [{"title": "减肥视频", "content": "今天开始..."}]
        msg = build_user_message(merged)
        assert "以下是本期发布的人设内容视频（共1条）" in msg
        assert "### 视频 1：减肥视频" in msg
        assert "【完整脚本】" in msg
        assert "请输出复盘报告。" in msg

    def test_separator_between_videos(self):
        merged = [
            {"title": "视频A", "content": "内容A"},
            {"title": "视频B", "content": "内容B"},
        ]
        msg = build_user_message(merged)
        assert "\n\n---\n\n" in msg

    def test_content_truncated_at_2000(self):
        """内容超过 2000 字时截断并注明"""
        long_content = "a" * 2500
        merged = [{"title": "测试", "content": long_content}]
        msg = build_user_message(merged)
        assert "...(已截断)" in msg
        # 截断后脚本部分不超过 2000 字 + 标注
        assert long_content[:2001] not in msg

    def test_content_not_truncated_under_2000(self):
        content = "a" * 1999
        merged = [{"title": "测试", "content": content}]
        msg = build_user_message(merged)
        assert "...(已截断)" not in msg

    def test_meta_fields_included(self):
        merged = [{
            "title": "测试视频",
            "content": "内容",
            "date": "2026-06-01",
            "video_type": "口播",
            "likes": "2000",
            "comments": "150",
            "total_plays": "50",
            "completion_rate": "40%",
            "five_sec_rate": "60%",
            "ad_spend": "500",
            "live_theme": "周一场",
        }]
        msg = build_user_message(merged)
        assert "发布日期: 2026-06-01" in msg
        assert "类型: 口播" in msg
        assert "点赞: 2000" in msg
        assert "评论: 150" in msg
        assert "播放量: 50万" in msg
        assert "完播率: 40%" in msg
        assert "5s完播率: 60%" in msg
        assert "投放金额: 500" in msg
        assert "所属直播场: 周一场" in msg

    def test_empty_content_no_script_block(self):
        """content="" 的追加行，不输出【完整脚本】块"""
        merged = [{"title": "无脚本视频", "content": "", "likes": "100"}]
        msg = build_user_message(merged)
        assert "【完整脚本】" not in msg

    def test_meta_fields_pipe_separated(self):
        merged = [{
            "title": "视频",
            "content": "内容",
            "likes": "100",
            "comments": "10",
        }]
        msg = build_user_message(merged)
        assert " | " in msg
