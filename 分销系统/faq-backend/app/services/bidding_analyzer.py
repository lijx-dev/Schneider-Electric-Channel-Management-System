"""
招标文件分析器
负责 PDF / Word 文本提取、关键词匹配检测、风险等级判断、生成结构化分析报告。

核心流程：
  PDF/Word文件 → 文本提取 → 关键词匹配(友商/施耐德) → 章节定位 → 风险判断 → 生成报告
"""
from __future__ import annotations

import io
import os
import re
import struct
from typing import Any

from app.core.logging import get_logger
from app.services.bidding_features import (
    COMPETITOR_FEATURES,
    COMPETITOR_RISK_INDICATORS,
    FAVORABLE_CLAUSES,
    PRODUCT_SERIES,
    REQUIRED_DOCUMENTS,
    SCHNEIDER_FEATURES,
    TENDER_BIDDING_REQUIREMENTS,
    TENDER_SECTIONS,
)

logger = get_logger(__name__)

# 允许的文件类型
ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "dot", "dotx"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    "application/msword",
    "application/vnd.ms-word",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


class BiddingAnalyzer:
    """招标文件分析器"""

    @staticmethod
    def validate_file(filename: str, content_type: str, file_size: int) -> str | None:
        """
        验证上传文件是否合法。
        返回错误信息字符串，如果合法则返回 None。
        """
        if not filename:
            return "文件名不能为空"

        extension = filename.split(".")[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            return "仅支持 PDF 和 Word（.doc/.docx/.dot/.dotx）格式文件"

        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            return "文件类型不合法，仅支持 PDF 和 Word 格式"

        if file_size == 0:
            return "文件不能为空"

        if file_size > MAX_FILE_SIZE:
            return f"文件过大，请上传小于 {MAX_FILE_SIZE // (1024 * 1024)}MB 的文件"

        return None

    @staticmethod
    def extract_text(file_content: bytes, filename: str = "") -> str:
        """
        根据文件扩展名自动选择 PDF 或 Word 文本提取方式。
        返回提取的全文文本。
        """
        extension = filename.split(".")[-1].lower() if "." in filename else ""

        if extension in ("docx", "dotx"):
            return BiddingAnalyzer._extract_text_from_docx(file_content)
        elif extension in ("doc", "dot"):
            return BiddingAnalyzer._extract_text_from_doc(file_content)
        else:
            return BiddingAnalyzer._extract_text_from_pdf(file_content)

    @staticmethod
    def _extract_text_from_pdf(file_content: bytes) -> str:
        """
        使用 pdfplumber 从 PDF 文件中提取文本。
        """
        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber_not_installed")
            raise RuntimeError("PDF 解析库未安装，请联系管理员")

        text_parts: list[str] = []
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                total_pages = len(pdf.pages)
                logger.info("pdf_opened", total_pages=total_pages)

                for page_num, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"\n=== 第{page_num}页 ===\n")
                        text_parts.append(page_text)

                full_text = "".join(text_parts)

                if not full_text.strip():
                    logger.warning("pdf_empty_text", total_pages=total_pages)
                    return ""

                logger.info(
                    "pdf_text_extracted",
                    total_pages=total_pages,
                    text_length=len(full_text),
                )
                return full_text

        except Exception as exc:
            logger.error("pdf_extract_failed", error=str(exc))
            raise RuntimeError(f"PDF 文本提取失败: {exc}") from exc

    @staticmethod
    def _extract_text_from_docx(file_content: bytes) -> str:
        """
        使用 python-docx 从 .docx / .dotx 文件中提取文本（含段落和表格）。
        """
        try:
            import docx
        except ImportError:
            logger.error("python_docx_not_installed")
            raise RuntimeError("Word 解析库未安装，请联系管理员")

        try:
            doc = docx.Document(io.BytesIO(file_content))
            text_parts: list[str] = []

            # 提取段落文本
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            # 提取表格文本
            for table in doc.tables:
                for row in table.rows:
                    row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_texts:
                        text_parts.append(" | ".join(row_texts))

            full_text = "\n".join(text_parts)

            if not full_text.strip():
                logger.warning("docx_empty_text")
                return ""

            logger.info("docx_text_extracted", text_length=len(full_text))
            return full_text

        except Exception as exc:
            # python-docx 对 .docx 格式解析失败时，尝试当作 ZIP 降级提取
            logger.warning("docx_parse_failed_trying_zip", error=str(exc))
            try:
                return BiddingAnalyzer._extract_text_from_docx_zip(file_content)
            except Exception as zip_exc:
                logger.error("docx_zip_fallback_failed", error=str(zip_exc))
                raise RuntimeError(f"Word 文档文本提取失败: {exc}") from exc

    @staticmethod
    def _extract_text_from_docx_zip(file_content: bytes) -> str:
        """
        .docx / .dotx 文件本质上是 ZIP 压缩包。
        当 python-docx 解析失败时，直接从 ZIP 中的 document.xml 提取纯文本。
        """
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            if "word/document.xml" not in zf.namelist():
                raise RuntimeError("文件中未找到 word/document.xml，可能不是有效的 .docx/.dotx 文件")
            xml_content = zf.read("word/document.xml")

        # 移除 XML 命名空间以便解析
        xml_text = xml_content.decode("utf-8", errors="ignore")
        xml_text = re.sub(r'xmlns[^=]*="[^"]*"', "", xml_text)
        xml_text = re.sub(r'w:', "", xml_text)

        root = ET.fromstring(xml_text)
        text_parts: list[str] = []

        for elem in root.iter():
            if elem.tag == "t" and elem.text:
                text_parts.append(elem.text)
            if elem.tag == "br":
                text_parts.append("\n")
            if elem.tag == "p":
                text_parts.append("\n")

        full_text = "".join(text_parts)
        if not full_text.strip():
            return ""

        logger.info("docx_zip_text_extracted", text_length=len(full_text))
        return full_text

    @staticmethod
    def _extract_text_from_doc(file_content: bytes) -> str:
        """
        从旧版 .doc / .dot 文件中提取文本。
        优先尝试 ZIP 解析（部分 .doc 文件实际为 .docx 格式），
        再尝试 raw byte 扫描提取 UTF-16LE 编码的中文字符序列。
        旧版二进制格式的提取为尽力而为模式，可能无法提取全部内容。
        """
        # 1. 先尝试 ZIP 解析（处理实际为 .docx/.dotx 格式的文件）
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
                if "word/document.xml" in zf.namelist():
                    logger.info("doc_is_actually_docx")
                    return BiddingAnalyzer._extract_text_from_docx_zip(file_content)
                else:
                    # 是 ZIP 但不是有效文档（如仅含主题的模板文件）
                    logger.warning("doc_is_zip_without_document")
                    return ""
        except (zipfile.BadZipFile, Exception):
            pass

        # 2. 尝试 raw byte 扫描（旧版 .doc 二进制格式）
        text_parts: list[str] = []
        i = 0
        data = file_content
        while i < len(data) - 1:
            code = struct.unpack("<H", data[i : i + 2])[0]
            if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF:
                try:
                    chunk = data[i : i + 200].decode("utf-16-le", errors="ignore")
                    readable = "".join(c for c in chunk if c.isprintable() or c in "\n\r\t")
                    if len(readable) > 5:
                        text_parts.append(readable)
                except Exception:
                    pass
            i += 2

        full_text = "\n".join(text_parts)
        lines = [l.strip() for l in full_text.split("\n") if len(l.strip()) > 3]
        seen: set[str] = set()
        unique_lines: list[str] = []
        for line in lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)

        result = "\n".join(unique_lines)
        if not result.strip():
            logger.warning("doc_empty_text")
            return ""

        logger.info("doc_text_extracted", text_length=len(result))
        return result

    @staticmethod
    def keyword_match(text: str) -> dict[str, Any]:
        """
        关键词匹配检测。
        在文本中搜索友商和施耐德品牌关键词，并判断风险等级。

        返回:
            {
                "competitors": [{"brand": "西门子", "matched_keywords": ["XL-IIIS", "西门子"]}],
                "schneider": {"matched_keywords": ["I-Line H", "施耐德"]},
                "risk_level": "高风险" | "中风险" | "低风险" | "未知",
                "risk_detail": "详细风险描述",
                "sections": {"技术参数": "第3页", "资质要求": "第15页"},
                "total_pages": 50,
                "text_length": 12345,
            }
        """
        result: dict[str, Any] = {
            "competitors": [],
            "schneider": {
                "brand": "施耐德",
                "matched_keywords": [],
            },
            "risk_level": "未知",
            "risk_detail": "",
            "sections": {},
            "bidding_requirements": {},
            "total_pages": 0,
            "text_length": len(text),
        }

        # 统计总页数（仅 PDF 有效，Word 文档无页码标记则为 0）
        page_markers = re.findall(r"=== 第(\d+)页 ===", text)
        if page_markers:
            result["total_pages"] = max(int(p) for p in page_markers)
        else:
            result["total_pages"] = 0

        # ---- 检测友商品牌 ----
        for comp_name, features in COMPETITOR_FEATURES.items():
            matched_kws: list[str] = []
            for kw in features["keywords"]:
                if kw.lower() in text.lower():
                    matched_kws.append(kw)
            if matched_kws:
                result["competitors"].append({
                    "brand": comp_name,
                    "matched_keywords": list(set(matched_kws)),
                })

        # ---- 检测施耐德品牌 ----
        schneider_matched: list[str] = []
        for kw in SCHNEIDER_FEATURES["keywords"]:
            if kw.lower() in text.lower():
                schneider_matched.append(kw)
        result["schneider"]["matched_keywords"] = list(set(schneider_matched))

        # ---- 检测章节位置 ----
        for section_name, keywords in TENDER_SECTIONS.items():
            for kw in keywords:
                # 在文本中按行查找，同时记录当前行在全文中的偏移位置
                lines = text.split("\n")
                offset = 0
                for line in lines:
                    if kw in line:
                        # 尝试找到该关键词所在页码
                        page_match = re.search(r"第(\d+)页", line)
                        if page_match:
                            result["sections"][section_name] = f"第{page_match.group(1)}页"
                        else:
                            # 使用当前行的偏移位置查找最近的页码标记
                            before = text[:offset]
                            page_before = re.findall(r"=== 第(\d+)页 ===", before)
                            if page_before:
                                result["sections"][section_name] = f"第{page_before[-1]}页"
                        break
                    offset += len(line) + 1  # +1 for \n
                if section_name in result["sections"]:
                    break

        # ---- 检测投标基本资料要求 ----
        for req_name, keywords in TENDER_BIDDING_REQUIREMENTS.items():
            matched_kws: list[str] = []
            for kw in keywords:
                if kw in text:
                    matched_kws.append(kw)
            if matched_kws:
                result["bidding_requirements"][req_name] = {
                    "matched_keywords": matched_kws,
                    "available": req_name in REQUIRED_DOCUMENTS,
                }

        # ---- 风险等级判断 ----
        has_competitor = len(result["competitors"]) > 0
        has_schneider = len(result["schneider"]["matched_keywords"]) > 0

        if has_competitor and not has_schneider:
            competitor_names = ", ".join(c["brand"] for c in result["competitors"])
            result["risk_level"] = "高风险"
            result["risk_detail"] = (
                f"检测到以下友商品牌关键词：{competitor_names}，"
                f"但未检测到施耐德品牌关键词。"
                f"招标文件可能被友商植入，建议人工复核技术参数部分，"
                f"确认是否存在对施耐德不利的排他性条款。"
            )
        elif has_competitor and has_schneider:
            competitor_names = ", ".join(c["brand"] for c in result["competitors"])
            result["risk_level"] = "中风险"
            result["risk_detail"] = (
                f"招标文件同时包含施耐德和友商品牌（{competitor_names}），"
                f"属于正常品牌描述。建议关注技术参数部分，"
                f"确认是否有对施耐德有利的独有参数被写入。"
            )
        elif not has_competitor and has_schneider:
            result["risk_level"] = "低风险"
            result["risk_detail"] = (
                "招标文件仅提及施耐德品牌，未检测到友商品牌关键词，"
                "属于对施耐德有利的标书。建议确认技术参数是否准确。"
            )
        else:
            result["risk_level"] = "未知"
            result["risk_detail"] = (
                "未检测到任何母线品牌关键词。"
                "招标文件可能未明确指定品牌，或品牌信息以图片形式存在，"
                "建议人工复核全文。"
            )

        return result

    @staticmethod
    def get_recommended_documents(keyword_result: dict[str, Any]) -> list[dict[str, str]]:
        """
        根据分析结果，推荐需要准备的投标文件列表。
        基础文件始终返回，并根据标书中检测到的投标基本资料要求追加对应文件。
        """
        # 基础文件：所有投标都需要
        base_docs = ["营业执照", "ISO认证", "产品检测报告", "法人授权书", "投标函", "报价表"]

        # 如果检测到施耐德品牌，追加认证文件
        if keyword_result["schneider"]["matched_keywords"]:
            base_docs.append("CE认证")
            base_docs.append("KEMA认证")
            base_docs.append("产品样本")
            base_docs.append("业绩证明")

        # 根据标书中检测到的投标基本资料要求，追加对应文件
        bidding_requirements = keyword_result.get("bidding_requirements", {})
        for req_name in bidding_requirements:
            if req_name in REQUIRED_DOCUMENTS and req_name not in base_docs:
                base_docs.append(req_name)

        docs = []
        for doc_name in base_docs:
            if doc_name in REQUIRED_DOCUMENTS:
                doc_info = REQUIRED_DOCUMENTS[doc_name]
                docs.append({
                    "name": doc_name,
                    "key": doc_info["key"],
                    "description": doc_info["description"],
                })

        return docs

    @staticmethod
    def deep_analyze(text: str, filename: str = "") -> dict[str, Any]:
        """
        智能深度分析招标文件。
        返回结构化分析报告，包含：
          - 总体判断（风险等级 + 一句话结论）
          - 施耐德有利条款检测（已植入 vs 缺失）
          - 友商植入痕迹检测
          - 产品匹配推荐（I-Line B/H/W 对比）
          - 投标策略建议
        """
        result: dict[str, Any] = {
            "filename": filename,
            "total_pages": 0,
            "text_length": len(text),
            "summary": "",
            "risk_level": "",
            "favorable_clauses": [],
            "missing_clauses": [],
            "competitor_traces": [],
            "product_match": {},
            "strategy": [],
        }

        # 统计总页数
        page_markers = re.findall(r"=== 第(\d+)页 ===", text)
        if page_markers:
            result["total_pages"] = max(int(p) for p in page_markers)

        # ---- 一、检测施耐德有利条款（已植入 vs 缺失） ----
        favorable_found: list[dict] = []
        favorable_missing: list[dict] = []

        for clause in FAVORABLE_CLAUSES:
            matched = any(kw in text for kw in clause["keywords"])
            if matched:
                favorable_found.append({
                    "name": clause["name"],
                    "threshold": clause["favorable_threshold"],
                    "analysis": clause["analysis_favorable"],
                    "products": clause["products"],
                })
            else:
                favorable_missing.append({
                    "name": clause["name"],
                    "threshold": clause["favorable_threshold"],
                    "risk": clause["risk_if_missing"],
                    "analysis": clause["analysis_missing"],
                    "products": clause["products"],
                })

        result["favorable_clauses"] = favorable_found
        result["missing_clauses"] = favorable_missing

        # ---- 二、检测友商植入痕迹 ----
        competitor_traces: list[dict] = []
        for indicator in COMPETITOR_RISK_INDICATORS:
            matched = any(kw in text for kw in indicator["keywords"])
            if matched:
                competitor_traces.append({
                    "name": indicator["name"],
                    "risk_pattern": indicator["risk_pattern"],
                    "risk_level": indicator["risk_level"],
                    "analysis": indicator["analysis"],
                    "possible_competitor": indicator["possible_competitor"],
                })
        result["competitor_traces"] = competitor_traces

        # ---- 三、产品匹配分析 ----
        product_scores: dict[str, int] = {}
        for product_name, product_params in PRODUCT_SERIES.items():
            score = 0
            param_matches: list[dict] = []
            for clause in FAVORABLE_CLAUSES:
                if product_name in clause["products"]:
                    if any(kw in text for kw in clause["keywords"]):
                        score += 1
                        param_matches.append({
                            "param": clause["name"],
                            "product_value": product_params.get(clause["id"], ""),
                            "status": "matched",
                        })

            product_scores[product_name] = {
                "score": score,
                "max_score": len([c for c in FAVORABLE_CLAUSES if product_name in c["products"]]),
                "full_name": product_params["full_name"],
                "positioning": product_params["positioning"],
            }

        # 排序产品匹配度
        rankings = sorted(
            product_scores.items(),
            key=lambda x: x[1]["score"] / max(x[1]["max_score"], 1),
            reverse=True,
        )

        best_product = rankings[0][0] if rankings else ""
        best_info = product_scores[best_product] if best_product else {}

        result["product_match"] = {
            "best_match": best_product,
            "best_full_name": best_info.get("full_name", ""),
            "rankings": [
                {
                    "product": name,
                    "full_name": info["full_name"],
                    "positioning": info["positioning"],
                    "score": info["score"],
                    "max_score": info["max_score"],
                    "match_rate": round(info["score"] / max(info["max_score"], 1) * 100),
                }
                for name, info in rankings
            ],
        }

        # ---- 四、总体判断 ----
        has_competitor_brand = False
        for comp_name, features in COMPETITOR_FEATURES.items():
            if any(kw.lower() in text.lower() for kw in features["keywords"]):
                has_competitor_brand = True
                break

        has_schneider_brand = any(
            kw.lower() in text.lower() for kw in SCHNEIDER_FEATURES["keywords"]
        )

        favorable_count = len(favorable_found)
        missing_count = len(favorable_missing)
        high_risk_missing = len([c for c in favorable_missing if c["risk"] == "高"])
        competitor_trace_count = len(competitor_traces)

        # 判断风险等级
        if has_competitor_brand and not has_schneider_brand:
            result["risk_level"] = "高风险"
            risk_label = "高风险"
        elif has_competitor_brand and has_schneider_brand:
            result["risk_level"] = "中风险"
            risk_label = "中风险"
        elif not has_competitor_brand and has_schneider_brand:
            result["risk_level"] = "低风险"
            risk_label = "低风险"
        else:
            result["risk_level"] = "未知"
            risk_label = "未知"

        # 生成总体判断
        if favorable_count >= 15:
            implantation_status = "已经进行了非常有效的植入"
        elif favorable_count >= 8:
            implantation_status = "已进行了部分植入，但仍有优化空间"
        elif favorable_count >= 3:
            implantation_status = "仅有少量植入，大部分核心壁垒条款缺失"
        else:
            implantation_status = "基本未被植入，核心壁垒条款严重缺失"

        if competitor_trace_count >= 5:
            competitor_status = "存在较多友商植入痕迹，需重点关注"
        elif competitor_trace_count >= 2:
            competitor_status = "存在少量友商植入痕迹"
        else:
            competitor_status = "未发现明显的友商定向植入痕迹"

        result["summary"] = (
            f"该招标文件处于「{risk_label}」状态。"
            f"我方{implantation_status}（已检测到{favorable_count}项有利条款，{missing_count}项缺失，其中{high_risk_missing}项高风险）。"
            f"{competitor_status}。"
            f"推荐使用 **{best_info.get('full_name', best_product)}** 进行投标。"
        )

        # ---- 五、投标策略建议 ----
        strategy: list[str] = []
        if high_risk_missing > 0:
            strategy.append(
                f"技术规范补充建议：重点补充{high_risk_missing}项高风险缺失条款，"
                f"包括抗震要求、KEMA/ASTA认证、制造商15年以上经验、消防喷淋试验等，"
                f"以建立技术壁垒。"
            )
        if best_product:
            strategy.append(
                f"推荐主投 **{best_info.get('full_name', best_product)}**，"
                f"其技术参数与招标文件要求匹配度最高。"
            )
        if favorable_count > 0:
            strategy.append(
                "在投标文件中，主动提交「优于技术规范的技术响应」，逐条列出超出招标要求的性能指标作为加分项。"
            )
        if competitor_trace_count > 0:
            strategy.append(
                "注意识别友商植入痕迹，在技术偏离表中针对性地提出我方更优方案。"
            )
        strategy.append(
            "建议在项目早期（技术规范起草阶段）即由我方人员介入，使用我方技术规范书模板作为底稿。"
        )
        result["strategy"] = strategy

        logger.info(
            "deep_analyze_complete",
            filename=filename,
            risk_level=result["risk_level"],
            favorable_count=favorable_count,
            missing_count=missing_count,
            competitor_traces=competitor_trace_count,
            best_product=best_product,
        )

        return result