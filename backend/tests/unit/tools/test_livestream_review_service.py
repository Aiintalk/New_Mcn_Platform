"""单元测试：livestream_review service 核心函数。"""
import pytest
from app.tools.livestream_review.service import (
    merge_scripts_and_excel,
    build_user_message,
    detect_has_excel,
)


# ---------- merge_scripts_and_excel ----------

class TestMergeScriptsAndExcel:
    def test_no_excel_returns_scripts_only(self):
        scripts = [{"title": "场次一", "content": "脚本内容一"}]
        result = merge_scripts_and_excel(scripts, [])
        assert len(result) == 1
        assert result[0]["title"] == "场次一"
        assert result[0]["content"] == "脚本内容一"
        assert result[0].get("gmv") is None

    def test_matched_excel_row_merged(self):
        scripts = [{"title": "双十一大促", "content": "开场话术..."}]
        excel = [{"live_theme": "双十一大促", "gmv": "100000", "peak_viewers": "5000"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert len(result) == 1
        assert result[0]["gmv"] == "100000"
        assert result[0]["peak_viewers"] == "5000"

    def test_fuzzy_match_by_date(self):
        scripts = [{"title": "6月15号直播", "content": "脚本"}]
        excel = [{"live_date": "6月15号", "gmv": "50000"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert result[0].get("gmv") == "50000"

    def test_unmatched_excel_rows_not_appended(self):
        """已确认：未匹配的 Excel 行不追加到结果（只保留有脚本内容的场次）"""
        scripts = [{"title": "场次A", "content": "内容A"}]
        excel = [
            {"live_theme": "场次A", "gmv": "1000"},
            {"live_theme": "场次B无对应脚本", "gmv": "2000"},
        ]
        result = merge_scripts_and_excel(scripts, excel)
        assert len(result) == 1
        assert result[0]["title"] == "场次A" or result[0]["gmv"] == "1000"

    def test_sorted_by_gmv_desc(self):
        scripts = [
            {"title": "低GMV场次", "content": "内容"},
            {"title": "高GMV场次", "content": "内容"},
        ]
        excel = [
            {"live_theme": "低GMV场次", "gmv": "1000"},
            {"live_theme": "高GMV场次", "gmv": "99000"},
        ]
        result = merge_scripts_and_excel(scripts, excel)
        assert float(result[0].get("gmv", "0")) > float(result[1].get("gmv", "0"))

    def test_no_gmv_sorted_last(self):
        scripts = [
            {"title": "有GMV场次", "content": "内容"},
            {"title": "无数据场次", "content": "内容"},
        ]
        excel = [{"live_theme": "有GMV场次", "gmv": "5000"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert result[0].get("gmv") == "5000"

    def test_title_replaced_by_live_theme_when_matched(self):
        scripts = [{"title": "文件名.docx", "content": "内容"}]
        excel = [{"live_theme": "双十一专场", "live_date": "文件名"}]
        result = merge_scripts_and_excel(scripts, excel)
        # 匹配时 title 替换为 live_theme
        assert result[0]["title"] == "双十一专场"

    def test_punctuation_normalized_in_matching(self):
        """清洗标点后匹配：去除 ，。！？、#@\s 全角空格"""
        scripts = [{"title": "6月，15号！直播", "content": "内容"}]
        excel = [{"live_theme": "6月15号直播", "gmv": "8888"}]
        result = merge_scripts_and_excel(scripts, excel)
        assert result[0].get("gmv") == "8888"


# ---------- detect_has_excel ----------

class TestDetectHasExcel:
    def test_has_gmv_returns_true(self):
        merged = [{"title": "场次", "content": "内容", "gmv": "10000"}]
        assert detect_has_excel(merged) is True

    def test_has_peak_viewers_returns_true(self):
        merged = [{"title": "场次", "content": "内容", "peak_viewers": "5000"}]
        assert detect_has_excel(merged) is True

    def test_has_conversions_returns_true(self):
        merged = [{"title": "场次", "content": "内容", "conversions": "100"}]
        assert detect_has_excel(merged) is True

    def test_no_data_fields_returns_false(self):
        merged = [{"title": "场次", "content": "脚本内容，无数据"}]
        assert detect_has_excel(merged) is False

    def test_empty_string_fields_returns_false(self):
        merged = [{"title": "场次", "content": "内容", "gmv": "", "peak_viewers": None}]
        assert detect_has_excel(merged) is False

    def test_any_item_has_data_returns_true(self):
        merged = [
            {"title": "场次一", "content": "内容"},
            {"title": "场次二", "content": "内容", "gmv": "5000"},
        ]
        assert detect_has_excel(merged) is True


# ---------- build_user_message ----------

class TestBuildUserMessage:
    def test_contains_total_count(self):
        merged = [
            {"title": "场次一", "content": "开场白内容"},
            {"title": "场次二", "content": "产品讲解"},
        ]
        msg = build_user_message(merged)
        assert "共2场" in msg

    def test_scene_header_format(self):
        merged = [{"title": "双十一", "content": "脚本"}]
        msg = build_user_message(merged)
        assert "### 场次 1：双十一" in msg

    def test_meta_parts_included(self):
        merged = [{
            "title": "场次",
            "content": "脚本",
            "live_date": "2026-06-15",
            "gmv": "50000",
            "peak_viewers": "8000",
        }]
        msg = build_user_message(merged)
        assert "日期: 2026-06-15" in msg
        assert "GMV: 50000元" in msg
        assert "峰值在线: 8000" in msg

    def test_content_truncated_at_3000_chars(self):
        long_content = "A" * 4000
        merged = [{"title": "长脚本", "content": long_content}]
        msg = build_user_message(merged)
        assert "...(已截断)" in msg
        # 截断后内容中不包含超过 3000 个 A 之后的多余字符（msg 总长 < 4000 + overhead）
        assert msg.count("A") == 3000

    def test_short_content_not_truncated(self):
        content = "短脚本内容"
        merged = [{"title": "场次", "content": content}]
        msg = build_user_message(merged)
        assert "...(已截断)" not in msg
        assert content in msg

    def test_complete_script_section_label(self):
        merged = [{"title": "场次", "content": "脚本内容"}]
        msg = build_user_message(merged)
        assert "【完整直播脚本】" in msg

    def test_meta_parts_separator_pipe(self):
        merged = [{
            "title": "场次",
            "content": "内容",
            "gmv": "1000",
            "conversions": "50",
        }]
        msg = build_user_message(merged)
        assert " | " in msg

    def test_empty_meta_fields_excluded(self):
        merged = [{"title": "场次", "content": "内容", "gmv": None, "peak_viewers": ""}]
        msg = build_user_message(merged)
        assert "GMV:" not in msg
        assert "峰值在线:" not in msg

    def test_multiple_scenes_separated(self):
        merged = [
            {"title": "场次一", "content": "内容一"},
            {"title": "场次二", "content": "内容二"},
        ]
        msg = build_user_message(merged)
        assert "场次 1：场次一" in msg
        assert "场次 2：场次二" in msg
        assert "\n\n---\n\n" in msg
