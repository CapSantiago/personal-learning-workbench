"""M0 UI only. It cannot import real study files or create a production database."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from uuid import uuid4

import streamlit as st

PROJECT = Path(__file__).resolve().parent
if str(PROJECT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT / "src"))

from plw_probe.core import create_demo_sources, initialize, list_imports, probe_import

ROOT = PROJECT / ".sandbox" / "m0"
TEXT_SAMPLE = ROOT / "sources" / "合成资料 中文 空格.txt"
PDF_SAMPLE = ROOT / "sources" / "合成 PDF 样本.pdf"

FORMULA_SAMPLE = r"""
### 机器人学习公式样例
行内公式：关节位置 $q_i$、角速度 $\dot q_i$，以及 $\tau = J^T F$。

雅可比矩阵：
$$
J = \begin{bmatrix} \partial x/\partial q_1 & \partial x/\partial q_2 \\
\partial y/\partial q_1 & \partial y/\partial q_2 \end{bmatrix}
$$

积分与分段函数：
$$
v(t)=\int_0^t a(s)\,ds,\qquad
f(x)=\begin{cases}x^2 & x\ge 0\\-x & x<0\end{cases}
$$

此页只渲染固定本地样例，不包含远程图片、字体或 HTML。
"""

st.set_page_config(page_title="PLW · M0 技术验证", page_icon="📘", layout="wide")
st.title("Personal Learning Workbench")
st.caption("M0 · 独立环境与合成数据技术验证")
st.info("当前是技术验证程序。仅接受本项目 .sandbox/m0/sources 内的合成文件，不导入真实学习资料。")

st.session_state.setdefault("source_path", str(TEXT_SAMPLE))
st.session_state.setdefault("operation_id", str(uuid4()))

if st.button("生成合成样例", key="generate"):
    try:
        examples = create_demo_sources(ROOT)
        initialize(ROOT)
        st.session_state["source_path"] = str(examples["chinese_text"])
        st.success("合成文本、PDF 和演示数据库已就绪。已有样例不会被覆盖。")
    except (OSError, ValueError, RuntimeError) as exc:
        st.error(f"生成失败：{exc}")

left, right = st.columns([3, 2])
with left:
    st.subheader("验证文件导入")
    st.caption("从资源管理器复制合成文件的绝对路径。重复提交相同操作 ID 应返回同一记录。")
    if st.button("使用新的操作 ID", key="new_operation"):
        st.session_state["operation_id"] = str(uuid4())
    with st.form("import_probe", clear_on_submit=False):
        st.text_input("合成文件绝对路径", key="source_path")
        mode = st.selectbox(
            "存储模式", ["managed_copy", "external_reference"], key="mode",
            format_func=lambda value: "托管复制 (managed_copy)" if value == "managed_copy" else "外部引用 (external_reference)",
        )
        st.text_input("操作 ID", key="operation_id")
        submitted = st.form_submit_button("提交验证")
    if submitted:
        try:
            record = probe_import(ROOT, st.session_state["source_path"], mode, st.session_state["operation_id"])
            st.success("提交成功；相同操作 ID 不会重复添加。")
            st.json(record)
        except Exception as exc:
            # Keep form values and expose the error without claiming completion.
            st.error(f"提交未完成：{type(exc).__name__}: {exc}")
    try:
        records = list_imports(ROOT)
        st.metric("已完成的合成资料记录", len(records))
        if records:
            st.dataframe(records, hide_index=True, width="stretch")
    except Exception as exc:
        st.error(f"读取验证记录失败：{type(exc).__name__}: {exc}")

with right:
    st.subheader("本地阅读入口")
    st.caption("PDF 使用系统默认阅读器；内嵌预览和阅读位置留待后续验证。")
    if st.button("用默认阅读器打开合成 PDF", key="open_pdf"):
        try:
            resolved = PDF_SAMPLE.resolve(strict=True)
            if resolved != PDF_SAMPLE.absolute() or PDF_SAMPLE.is_symlink() or PDF_SAMPLE.is_junction():
                raise ValueError("PDF 必须是合成目录内的普通文件。")
            # Validate every ancestor, not just the final file.
            for parent in PDF_SAMPLE.parents:
                if parent.is_symlink() or parent.is_junction():
                    raise ValueError("PDF 路径包含链接。")
            os.startfile(str(resolved))
            st.success("已向 Windows 提交打开请求；是否正确显示需查看阅读器。")
        except (OSError, ValueError) as exc:
            st.error(f"无法打开 PDF：{exc}")
    st.code(str(PDF_SAMPLE), language=None)
    st.markdown(FORMULA_SAMPLE, unsafe_allow_html=False)

with st.expander("范围与下一步"):
    st.write("本轮只验证环境、路径、幂等提交、SQLite 和离线公式。课程、任务、正式笔记、完整备份恢复均未实现。")
    st.write("技术验证通过后进入 M1；真实资料需等 M2 完整恢复演练通过后再导入。")
