"""
app/evaluation/models/__init__.py

聚合所有 eval_ ORM 模型 import，供 `app.models.__init__` 跨包注册使用。
"""
from app.evaluation.models.case_result import EvalCaseResult
from app.evaluation.models.dimension import EvalDimension
from app.evaluation.models.human_label import EvalHumanLabel
from app.evaluation.models.judge_model import EvalJudgeModel
from app.evaluation.models.rubric import EvalRubric
from app.evaluation.models.run import EvalRun
from app.evaluation.models.schedule_policy import EvalSchedulePolicy
from app.evaluation.models.score import EvalScore
from app.evaluation.models.strategy import EvalStrategy
from app.evaluation.models.test_case import EvalTestCase
from app.evaluation.models.version import EvalVersion

__all__ = [
    "EvalCaseResult",
    "EvalDimension",
    "EvalHumanLabel",
    "EvalJudgeModel",
    "EvalRubric",
    "EvalRun",
    "EvalSchedulePolicy",
    "EvalScore",
    "EvalStrategy",
    "EvalTestCase",
    "EvalVersion",
]
