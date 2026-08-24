# -*- coding: utf-8 -*-
"""深度调查 Agent 的 LLM API 可视化配置界面（tkinter 实现，标准库自带）。

提供 API 地址 / 密钥 / 模型名 / 温度 / 超时等字段的填写、保存与清除。
配置写入本地未入库文件 `llm_config.local.json`（含 apikey，已 gitignore）。

运行方式（项目根目录）：
  PYTHONPATH=src python -m sec_agent.deep_agent.config_gui

说明：本界面管理的是本地配置文件；若同时设置了 LLM_* 环境变量，环境变量优先级更高，
会覆盖本地文件中的同名项。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .config import (
    api_config_path,
    clear_api_config,
    load_api_config_file,
    save_api_config,
)

# 表单字段：(文件 key, 显示标签, 是否脱敏显示)
FIELDS = [
    ("base_url", "模型地址 (Base URL)", False),
    ("api_key", "API 密钥 (API Key)", True),
    ("model", "模型名称 (Model)", False),
    ("temperature", "温度 (Temperature)", False),
    ("timeout", "超时秒数 (Timeout)", False),
]


class APIConfigWindow:
    """API 配置窗口。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("深度调查 Agent · API 配置")
        self.root.resizable(False, False)

        self._vars: dict[str, tk.StringVar] = {}
        self._build()
        self._load_existing()

    # ------------------------------------------------------------------ 界面
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 5}
        frame = tk.Frame(self.root, padx=12, pady=12)
        frame.pack(fill="both", expand=True)

        for i, (key, label, secret) in enumerate(FIELDS):
            tk.Label(frame, text=label, anchor="w", width=22).grid(
                row=i, column=0, sticky="w", **pad
            )
            var = tk.StringVar()
            entry = tk.Entry(frame, textvariable=var, width=52, show="*" if secret else "")
            entry.grid(row=i, column=1, sticky="we", **pad)
            self._vars[key] = var

        btn_row = len(FIELDS)
        btns = tk.Frame(frame)
        btns.grid(row=btn_row, column=0, columnspan=2, pady=(16, 4))
        tk.Button(btns, text="保存配置", width=14, command=self._on_save).pack(
            side="left", padx=6
        )
        tk.Button(btns, text="清除配置", width=14, command=self._on_clear).pack(
            side="left", padx=6
        )

        self.status = tk.Label(
            frame, text="", anchor="w", fg="#555", wraplength=420, justify="left"
        )
        self.status.grid(row=btn_row + 1, column=0, columnspan=2, sticky="we", pady=(8, 0))

    # ------------------------------------------------------------------ 逻辑
    def _load_existing(self) -> None:
        data = load_api_config_file()
        for key, _, _ in FIELDS:
            self._vars[key].set(str(data.get(key, "")))
        if data:
            self._set_status("已读取本地配置：%s" % api_config_path())
        else:
            self._set_status("尚未保存配置（未设置时回退到环境变量或默认值）")

    def _on_save(self) -> None:
        try:
            path = save_api_config(
                base_url=self._vars["base_url"].get(),
                api_key=self._vars["api_key"].get(),
                model=self._vars["model"].get() or "deepseek-chat",
                temperature=self._vars["temperature"].get() or 0.0,
                timeout=self._vars["timeout"].get() or 90,
            )
        except (TypeError, ValueError) as exc:
            messagebox.showerror("保存失败", "字段格式错误：\n%s" % exc)
            return
        self._set_status("已保存到：%s" % path)
        messagebox.showinfo("保存成功", "配置已保存到：\n%s" % path)

    def _on_clear(self) -> None:
        if not messagebox.askyesno(
            "确认清除", "确定清除已保存的 API 配置吗？\n（将删除本地配置文件）"
        ):
            return
        removed = clear_api_config()
        for key, _, _ in FIELDS:
            self._vars[key].set("")
        self._set_status("已清除本地配置" if removed else "本地无配置可清除")

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)


def main() -> None:
    root = tk.Tk()
    APIConfigWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
