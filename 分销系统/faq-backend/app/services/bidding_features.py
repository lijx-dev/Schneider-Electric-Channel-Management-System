"""
招标文件分析特征库
定义友商品牌关键词、施耐德品牌关键词、招标文件章节关键词，用于检测标书中的品牌植入情况。
所有关键词均来源于现有产品样本和FAQ知识库，确保真实可查。
"""

# ============================================================
# 友商特征 — 检测标书中是否出现友商品牌
# 每个友商包含：品牌名称、关键词列表、独有系列型号
# ============================================================
COMPETITOR_FEATURES = {
    "西门子": {
        "brand": "西门子",
        "keywords": [
            "西门子", "西門子", "镇江西门子", "镇江西门子",
            "SIEMENS", "Siemens",
            "XL-IIIS", "XL-IIIS", "XL-IIIS密集型",
            "XL-III", "XLC-III", "XLC-IIIH",
            "XLB-III", "XLB-III铝合金",
            "XL-ⅡS", "XL-IIS",
        ],
        "series": ["XL-IIIS", "XL-III", "XLB-III", "XLC-IIIH", "XL-ⅡS"],
        "unique_params": [],
    },
    "伊顿": {
        "brand": "伊顿",
        "keywords": [
            "伊顿", "Eaton", "EATON",
            "XAP-B", "XAP-C", "XAP-HR", "XAP-HS", "XAP-J", "XAP-S",
            "XAP Track", "XAP Track Pro",
            "伊顿XAP", "伊顿母线",
        ],
        "series": ["XAP-B", "XAP-C", "XAP-HR", "XAP-HS", "XAP-J", "XAP-S", "XAP Track", "XAP Track Pro"],
        "unique_params": [],
    },
    "ABB": {
        "brand": "ABB",
        "keywords": ["ABB", "ABB母线", "ABB Busway"],
        "series": [],
        "unique_params": [],
    },
    "LS": {
        "brand": "LS",
        "keywords": ["LS", "LG", "LS母线", "LS电缆", "韩国LS"],
        "series": [],
        "unique_params": [],
    },
    "罗格朗": {
        "brand": "罗格朗",
        "keywords": ["罗格朗", "Legrand", "罗格朗母线"],
        "series": [],
        "unique_params": [],
    },
    "正泰": {
        "brand": "正泰",
        "keywords": ["正泰", "正泰母线", "CHINT", "Chint"],
        "series": [],
        "unique_params": [],
    },
    "德力西": {
        "brand": "德力西",
        "keywords": ["德力西", "DELIXI", "德力西母线"],
        "series": [],
        "unique_params": [],
    },
}

# ============================================================
# 施耐德特征 — 检测标书中是否已有施耐德品牌植入
# ============================================================
SCHNEIDER_FEATURES = {
    "brand": "施耐德",
    "keywords": [
        "施耐德", "Schneider", "SCHNEIDER", "施耐德电气",
        "I-Line", "I-LINE", "Iline",
        "I-Line H", "I-Line HL", "I-Line HN",
        "I-Line V", "I-Line W", "I-Line C", "I-Line B",
        "Canalis", "CANALIS",
        "Square D", "SQUARE D",
        "施耐德母线", "施耐德广州",
    ],
    "series": [
        "I-Line H", "I-Line HL", "I-Line HN",
        "I-Line V", "I-Line W", "I-Line C", "I-Line B",
        "Canalis",
    ],
    "required_certifications": [
        "KEMA", "KEMA-KEUR", "CE",
    ],
}

# ============================================================
# 招标文件章节关键词 — 用于定位关键章节
# ============================================================
TENDER_SECTIONS = {
    "技术参数": ["技术参数", "参数表", "规格参数", "技术要求", "技术规格", "性能参数"],
    "资质要求": ["资质要求", "认证要求", "资格条件", "投标人资格", "资格审查"],
    "评分标准": ["评分标准", "评标办法", "打分标准", "评审办法", "综合评分"],
    "业绩要求": ["业绩要求", "工程经验", "类似业绩", "项目业绩", "同类项目"],
    "供货范围": ["供货范围", "供货清单", "货物清单", "设备清单", "供货一览表"],
    "付款方式": ["付款方式", "付款条件", "结算方式", "支付方式"],
    "保修条款": ["保修", "质保", "售后服务", "维护保养", "保修期"],
}

# ============================================================
# 投标常用文件清单 — 根据分析结果推荐下载的文件
# ============================================================
REQUIRED_DOCUMENTS = {
    "营业执照": {"key": "business_license", "description": "营业执照副本（加盖公章）"},
    "ISO认证": {"key": "iso_cert", "description": "ISO 9001质量管理体系认证证书"},
    "CE认证": {"key": "ce_cert", "description": "CE认证证书"},
    "KEMA认证": {"key": "kema_cert", "description": "KEMA-KEUR认证证书"},
    "产品检测报告": {"key": "test_report", "description": "国家认可实验室出具的产品检测报告"},
    "业绩证明": {"key": "performance", "description": "近三年类似项目业绩证明"},
    "产品样本": {"key": "product_catalog", "description": "产品电子版样本"},
    "法人授权书": {"key": "authorization", "description": "法定代表人授权委托书"},
    "投标函": {"key": "bid_letter", "description": "投标函"},
    "报价表": {"key": "price_list", "description": "投标报价表"},
}