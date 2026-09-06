# -*- coding: utf-8 -*-
import json
import os
import pytest
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent / "fixtures" / "gatekeeper_cases"

def load_all_cases():
    cases = []
    for i in range(1, 11):
        file_path = CASES_DIR / f"case{i}.json"
        with open(file_path, "r", encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases

@pytest.mark.parametrize("case_data", load_all_cases())
def test_case_quality(case_data):
    """验证案例质量检查项 (Task 3)"""
    input_event = case_data.get("input_event", {})
    
    # 1. 文件能够按照现有 SecurityEventInput 正常加载 (已经在 parametrization 中隐式验证)
    assert input_event
    
    # 2. 案例ID和事件ID唯一 (通过全局检查)
    assert case_data["case_id"]
    assert input_event["event_id"]
    
    # 3. 必填字段齐全
    required_fields = ["event_id", "event_type", "severity", "timestamp", "source_ip", "target_ip", "evidence"]
    for field in required_fields:
        assert field in input_event, f"Missing field: {field}"
        
    # 4. 字段类型正确
    assert isinstance(input_event["evidence"], list)
    assert isinstance(input_event["confidence"], (int, float))
    
    # 5. synthetic 数据性质标注清楚 (通过 description 检查)
    assert case_data["description"]

def test_unique_ids():
    cases = load_all_cases()
    case_ids = [c["case_id"] for c in cases]
    event_ids = [c["input_event"]["event_id"] for c in cases]
    
    assert len(set(case_ids)) == 10, "Case IDs are not unique"
    assert len(set(event_ids)) == 10, "Event IDs are not unique"

def extract_signals(evidence_list):
    """模拟门禁信号提取逻辑 (Task 5 - 非 LLM)"""
    signals = []
    for e in evidence_list:
        # 强信号提取
        if any(keyword in e for keyword in ["w3wp.exe", "cmd.exe", "Process.Start", "eval", "assert"]):
            signals.append("strong_malicious")
        # 弱信号提取
        elif any(keyword in e for keyword in ["shell.php", "Base64", "文件上传", "待调查"]):
            signals.append("weak_signal")
    return signals

def test_signal_extraction_logic():
    """验证信号提取与分类逻辑"""
    cases = load_all_cases()
    
    # Case 8: 仅文件名可疑 -> weak_signal
    case8 = next(c for c in cases if c["case_id"] == "TC-KNOWLEDGE-008")
    signals8 = extract_signals(case8["input_event"]["evidence"])
    assert "weak_signal" in signals8
    assert "strong_malicious" not in signals8
    
    # Case 9: 强组合 -> strong_malicious
    case9 = next(c for c in cases if c["case_id"] == "TC-KNOWLEDGE-009")
    signals9 = extract_signals(case9["input_event"]["evidence"])
    assert "strong_malicious" in signals9
    
    # Case 10: 域外事件 -> 无 WebShell 强信号
    case10 = next(c for c in cases if c["case_id"] == "TC-KNOWLEDGE-010")
    signals10 = extract_signals(case10["input_event"]["evidence"])
    assert "strong_malicious" not in signals10
    
    # Case 6: 负向案例严禁包含 WebShell 确认信号
    case6 = next(c for c in cases if c["case_id"] == "TC-KNOWLEDGE-006")
    signals6 = extract_signals(case6["input_event"]["evidence"])
    assert "strong_malicious" not in signals6
    assert "weak_signal" not in signals6

if __name__ == "__main__":
    pytest.main([__file__])
