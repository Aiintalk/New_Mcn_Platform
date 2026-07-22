"""
app/evaluation/constants.py

AIGC 评测模块常量：tool_code、触发类型、运行状态、默认策略名、默认适配器。
一期 tool_code 固定为 qianchuan-writer；适配器固定为 yunwu。
"""

# 一期被测工具：千川仿写
EVAL_TOOL_QIANCHUAN_WRITER = "qianchuan-writer"

# eval_runs.trigger_type 取值
TRIGGER_TYPE_MANUAL = "manual"
TRIGGER_TYPE_AUTO_ON_VERSION_CREATE = "auto_on_version_create"
TRIGGER_TYPE_SCHEDULED = "scheduled"

# eval_runs.status 取值
RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"

# 一期所有 run 绑定的默认策略
DEFAULT_STRATEGY_NAME = "default"

# 一期唯一启用的适配器
DEFAULT_ADAPTER = "yunwu"

# eval_judge_models.applicable_output_type 白名单
JUDGE_OUTPUT_TYPE_COPY = "copy"
JUDGE_OUTPUT_TYPE_VIDEO = "video"
JUDGE_OUTPUT_TYPE_AUDIO = "audio"
JUDGE_OUTPUT_TYPES = {
    JUDGE_OUTPUT_TYPE_COPY,
    JUDGE_OUTPUT_TYPE_VIDEO,
    JUDGE_OUTPUT_TYPE_AUDIO,
}
