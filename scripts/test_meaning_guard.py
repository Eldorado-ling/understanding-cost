"""Pure in-memory checks for obvious non-definitions in term grounding.

This finite guard is not a semantic evaluator or evidence of learner mastery.
"""

from __future__ import annotations

import copy
import unittest

import text_learning as policy


def grounding(term="聚焦圆锥", what="用位置呈现教学候选优先次序的表示"):
    return {
        "term": term,
        "what_it_is": what,
        "owner_scope": "当前学习任务的候选知识点",
        "role_here": "辅助比较下一步先学什么",
        "relation_direction": "候选证据影响排序位置",
    }


class MeaningGuardTests(unittest.TestCase):
    def test_previous_self_referential_definition_is_rejected(self):
        item = grounding(what="聚焦圆锥就是聚焦圆锥。")
        with self.assertRaisesRegex(policy.TextPolicyError, "重复为其自身"):
            policy._validate_term_grounding([item["term"]], [item])

    def test_chinese_repetition_variants_are_rejected(self):
        for text in ("聚焦圆锥", "聚焦圆锥是聚焦圆锥", "所谓聚焦圆锥，就是聚焦圆锥。",
                     "聚焦圆锥指的就是聚焦圆锥", "聚焦圆锥的意思是聚焦圆锥",
                     "聚焦圆锥就是一种聚焦圆锥", "“聚焦圆锥”就是“聚焦圆锥”。"):
            with self.subTest(text=text), self.assertRaisesRegex(policy.TextPolicyError, "重复为其自身"):
                policy._validate_term_grounding(["聚焦圆锥"], [grounding(what=text)])

    def test_english_repetition_case_whitespace_and_articles_are_rejected(self):
        for text in ("Focus cone is Focus cone", "FOCUS CONE IS FOCUS CONE.",
                     "Focus   cone\nmeans\tFocus cone", "A focus cone is a focus cone.",
                     "Focus cone refers to the focus cone", "Focus cone is defined as Focus cone",
                     "'Focus cone' is 'Focus cone'."):
            item = grounding("Focus cone", text)
            with self.subTest(text=text), self.assertRaisesRegex(policy.TextPolicyError, "重复为其自身"):
                policy._validate_term_grounding([item["term"]], [item])

    def test_each_meaning_field_rejects_obvious_placeholder_values(self):
        for field in ("what_it_is", "owner_scope", "role_here", "relation_direction"):
            for value in ("不知道", "待解释", "待补充", "TODO", "ＴＯＤＯ", " tbd. ",
                          "[placeholder]", "UNKNOWN", "I don't know", "...", "？？？"):
                item = grounding()
                item[field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(policy.TextPolicyError, field):
                    policy._validate_term_grounding([item["term"]], [item])

    def test_empty_or_whitespace_fields_still_fail_existing_nonempty_guard(self):
        for field in ("what_it_is", "owner_scope", "role_here", "relation_direction"):
            for value in ("", " \n\t "):
                item = grounding()
                item[field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(policy.TextPolicyError, "非空字符串"):
                    policy._validate_term_grounding([item["term"]], [item])

    def test_short_specific_meanings_are_not_rejected_for_length(self):
        item = {"term": "n", "what_it_is": "整数", "owner_scope": "杯数",
                "role_here": "计数", "relation_direction": "加一"}
        self.assertEqual(policy._validate_term_grounding(["n"], [item]), [item])

    def test_concrete_definition_can_repeat_term_without_being_tautological(self):
        item = grounding(what="聚焦圆锥是一种显示候选学习次序的表示；位置不证明掌握程度。")
        self.assertEqual(policy._validate_term_grounding([item["term"]], [item]), [item])
        english = grounding("Focus cone", "A focus cone is a display of candidate learning priorities.")
        self.assertEqual(policy._validate_term_grounding([english["term"]], [english]), [english])

    def test_a_placeholder_word_can_itself_be_the_term_being_explained(self):
        item = grounding("TODO", "标记尚待完成工作的文字")
        self.assertEqual(policy._validate_term_grounding(["TODO"], [item]), [item])

    def test_normal_definition_may_discuss_unknowns_or_pending_actions(self):
        item = grounding("待办", "记录尚未完成的动作，而不是把待补充当成具体内容")
        self.assertEqual(policy._validate_term_grounding(["待办"], [item]), [item])

    def test_existing_later_declared_dependency_rule_is_preserved(self):
        items = [grounding("参数", "用于改变关键帧的数值"),
                 grounding("关键帧", "保存指定状态的记录")]
        with self.assertRaisesRegex(policy.TextPolicyError, "尚未落地"):
            policy._validate_term_grounding(["参数", "关键帧"], items)
        reordered = [items[1], items[0]]
        self.assertEqual(policy._validate_term_grounding(["参数", "关键帧"], reordered), reordered)

    def test_ascii_dependency_next_to_chinese_and_identifier_boundary_are_preserved(self):
        items = [grounding("返回值", "x表示输入"), grounding("x", "一个输入数值")]
        with self.assertRaisesRegex(policy.TextPolicyError, "尚未落地"):
            policy._validate_term_grounding(["返回值", "x"], items)
        items[0]["what_it_is"] = "max 表示求最大数的操作"
        self.assertEqual(policy._validate_term_grounding(["返回值", "x"], items), items)

    def test_validation_does_not_modify_input(self):
        item = grounding()
        before = copy.deepcopy(item)
        policy._validate_term_grounding([item["term"]], [item])
        self.assertEqual(item, before)


if __name__ == "__main__":
    unittest.main()
