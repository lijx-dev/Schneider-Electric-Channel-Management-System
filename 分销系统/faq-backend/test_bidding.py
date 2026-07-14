#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""招标文件分析功能测试"""
from app.services.bidding_features import COMPETITOR_FEATURES, SCHNEIDER_FEATURES, TENDER_SECTIONS, REQUIRED_DOCUMENTS
from app.services.bidding_analyzer import BiddingAnalyzer

# 测试1: 关键词匹配（友商+施耐德混合）
text = "第一章 技术参数\n本项目采用施耐德 I-Line H 系列母线槽，额定电流 1000A。\n同时可选用西门子 XL-IIIS 密集型母线槽作为备选方案。\n投标人需提供 KEMA 认证证书和 CE 认证证书。\n详见第三章评分标准。"

result = BiddingAnalyzer.keyword_match(text)
print("=== 测试1: 混合品牌(中风险) ===")
print(f"风险等级: {result['risk_level']}")
print(f"风险详情: {result['risk_detail']}")
print(f"友商: {result['competitors']}")
print(f"施耐德关键词: {result['schneider']['matched_keywords']}")
print(f"章节: {result['sections']}")
assert result["risk_level"] == "中风险", f"预期中风险，实际{result['risk_level']}"
print("PASS\n")

# 测试2: 纯友商(高风险)
text2 = "本工程采用西门子 XL-IIIS 密集型母线槽，额定电流 2000A，需提供 ISO 认证。"
result2 = BiddingAnalyzer.keyword_match(text2)
print("=== 测试2: 纯友商(高风险) ===")
print(f"风险等级: {result2['risk_level']}")
assert result2["risk_level"] == "高风险", f"预期高风险，实际{result2['risk_level']}"
print("PASS\n")

# 测试3: 纯施耐德(低风险)
text3 = "本工程采用施耐德 I-Line H 系列母线槽，额定电流 2500A。"
result3 = BiddingAnalyzer.keyword_match(text3)
print("=== 测试3: 纯施耐德(低风险) ===")
print(f"风险等级: {result3['risk_level']}")
assert result3["risk_level"] == "低风险", f"预期低风险，实际{result3['risk_level']}"
print("PASS\n")

# 测试4: 无品牌(未知)
text4 = "本工程采用密集型母线槽，额定电流 1000A，需提供相关认证。"
result4 = BiddingAnalyzer.keyword_match(text4)
print("=== 测试4: 无品牌(未知) ===")
print(f"风险等级: {result4['risk_level']}")
assert result4["risk_level"] == "未知", f"预期未知，实际{result4['risk_level']}"
print("PASS\n")

# 测试5: 推荐文件
docs = BiddingAnalyzer.get_recommended_documents(result)
print("=== 测试5: 推荐文件 ===")
for doc in docs:
    print(f"  {doc['name']}: {doc['description']}")
assert len(docs) >= 6, f"预期至少6个文件，实际{len(docs)}"
print("PASS\n")

# 测试6: 伊顿检测
text6 = "欢迎使用伊顿 XAP-B 系列密集型母线槽和 XAP-C 紧凑型母线槽。"
result6 = BiddingAnalyzer.keyword_match(text6)
print("=== 测试6: 伊顿检测 ===")
print(f"风险等级: {result6['risk_level']}")
print(f"友商: {result6['competitors']}")
assert result6["risk_level"] == "高风险", f"预期高风险，实际{result6['risk_level']}"
assert len(result6["competitors"]) == 1, f"预期1个友商，实际{len(result6['competitors'])}"
print("PASS\n")

# 测试7: 文件验证
print("=== 测试7: 文件验证 ===")
assert BiddingAnalyzer.validate_file("test.pdf", "application/pdf", 1000) is None
assert BiddingAnalyzer.validate_file("test.docx", "application/pdf", 1000) is not None
assert BiddingAnalyzer.validate_file("", "application/pdf", 1000) is not None
assert BiddingAnalyzer.validate_file("test.pdf", "application/pdf", 0) is not None
assert BiddingAnalyzer.validate_file("test.pdf", "application/pdf", 30 * 1024 * 1024) is not None
print("PASS\n")

print("=" * 50)
print("所有测试通过!")