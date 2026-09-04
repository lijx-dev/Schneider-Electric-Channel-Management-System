"""端到端测试：专员提交申报 -> 经理查看并审批

模拟修复后前端提交格式（predefined + custom 含 text_list 数据）。
"""
import json
import sys
import httpx

# 与后端同一配置生成 token
from app.core.security import create_access_token

SPECIALIST_ID = 'test-specialist-001'  # 赵专员
MANAGER_ID = 'test-manager-001'        # 张经理
BASE = 'http://127.0.0.1:8011'

results = []

def log(name, ok, detail=''):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

def main():
    sp_token = create_access_token(SPECIALIST_ID)
    mg_token = create_access_token(MANAGER_ID)
    headers_sp = {"Authorization": f"Bearer {sp_token}"}
    headers_mg = {"Authorization": f"Bearer {mg_token}"}
    client = httpx.Client(base_url=BASE, timeout=30, trust_env=False)

    # ── 1. 专员加载表单配置（text_list 为主） ──
    r = client.get('/api/recognition/submissions/form-config',
                   params={'type': 'distributor_mentor'}, headers=headers_sp)
    cfg = r.json()
    ok = cfg.get('code') == 0 and cfg.get('data', {}).get('items')
    log('专员加载表单配置', ok, f"http={r.status_code} items={len(cfg.get('data', {}).get('items') or [])}")

    # ── 2. 专员提交申报（模拟修复后前端 text_list 有值） ──
    content_json = {
        "predefined": {
            "compliant_months": ["2026-06", "2026-07"],
            "improvement_cases": ["优化了季度报备审核流程"],
            "revenue_growth": ["东区分销商月度采购增长15%"],
            "capability_cases": ["组织两场新员工产品培训"]
        },
        "custom": [
            {"name": "跨区协作", "description": "提前交付南区大客户订单"}
        ]
    }
    r = client.post('/api/recognition/submissions', headers=headers_sp, json={
        "submission_type": "distributor_mentor",
        "content_json": content_json,
        "quarter": 3,
        "year": 2026,
        "submission_month": "2026-09"
    })
    body = r.json()
    ok = r.status_code == 200 and body.get('code') == 0 and body.get('data', {}).get('id')
    sub_id = body.get('data', {}).get('id')
    log('专员提交申报', ok, f"submission_id={sub_id}")

    if ok:
        # 校验入库 content_json 完整
        saved = body['data']['content_json']
        saved_content = json.loads(saved) if isinstance(saved, str) else saved
        text_ok = (saved_content.get('predefined', {}).get('compliant_months') == ['2026-06', '2026-07']
                   and saved_content.get('custom', [{}])[0].get('name') == '跨区协作')
        log('申报内容完整入库(模拟修复后前端格式)', text_ok, json.dumps(saved_content, ensure_ascii=False)[:200])

    # ── 3. 经理查看全部申报 ──
    r = client.get('/api/recognition/submissions/all', headers=headers_mg)
    body = r.json()
    data = body.get('data') or []
    mine = [s for s in data if s.get('status') == 'submitted' and s.get('applicant_id') == SPECIALIST_ID]
    log('经理查看申报列表', body.get('code') == 0 and len(data) > 0, f"total={len(data)} submitted_visible={len(mine)}")

    if mine:
        s = mine[0]
        content = s.get('content_json') or {}
        if isinstance(content, str):
            content = json.loads(content)
        predefined = content.get('predefined', {})
        full_ok = predefined.get('compliant_months') == ['2026-06', '2026-07'] and \
                  predefined.get('improvement_cases') == ['优化了季度报备审核流程']
        log('经理看到完整申报内容(text_list值完整)', full_ok, json.dumps(predefined, ensure_ascii=False)[:200])

        # ── 4. 经理审批通过 ──
        sid = s['id']
        r = client.post(f'/api/recognition/submissions/{sid}/review', headers=headers_mg, json={
            "action": "approve",
            "review_comment": "测试审批通过",
            "review_score": 4
        })
        body = r.json()
        ok = body.get('code') == 0 and body.get('data', {}).get('status') == 'approved'
        log('经理审批通过', ok, f"status={body.get('data', {}).get('status')}")

        # ── 5. 验证对象变更 ──
        r = client.get('/api/recognition/submissions', headers=headers_sp)
        mine_after = [s for s in (r.json().get('data') or []) if s.get('id') == sid]
        if mine_after:
            log('专员端状态同步为已通过', mine_after[0].get('status') == 'approved',
                f"status={mine_after[0].get('status')}")
    else:
        log('经理看到完整申报内容', False, '未找到刚提交的申报')

    # ── 汇总 ──
    failed = [r for r in results if not r[1]]
    print('=' * 50)
    if failed:
        print(f'FAILED: {len(failed)}/{len(results)}')
        for name, ok, detail in failed:
            print(f'  - {name}: {detail}')
        sys.exit(1)
    print(f'ALL {len(results)} TESTS PASSED')

if __name__ == '__main__':
    main()