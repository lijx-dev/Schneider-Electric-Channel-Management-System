"""端到端测试：销售给渠道专员评分全流程（销售自选专员，每月最多4位）

1. 销售查看本月评分状态（全部专员列表 + rated_count/max_specialists）
2. 销售为选中的专员提交评分（4维度）
3. 重复提交校验（同销售同专员同月不可重复）
4. 非专员目标被拒 / 目标不存在被拒
5. 超过每月4位上限被拒
6. 专员端查看匿名汇总结果
7. 经理端查看明细分
8. 非销售角色访问被拒(403)
"""
import sqlite3
import sys
import httpx

from app.core.security import create_access_token

SALES_1 = 'test-sales-001'          # 李销售
SALES_2 = 'test-sales-002'          # 王销售
SPECIALIST_1 = 'test-specialist-001'  # 赵专员
SPECIALIST_2 = 'test-specialist-002'  # 钱专员
SPECIALIST_3 = 'test-specialist-003'  # 补位专员
SPECIALIST_4 = 'test-specialist-004'  # 补位专员
SPECIALIST_5 = 'test-specialist-005'  # 补位专员
DISTRIBUTOR = 'test-distributor-001'  # 分销商（非专员）
MANAGER = 'test-manager-001'         # 张经理
BASE = 'http://127.0.0.1:8011'
MONTH = '2026-09'

results = []


def log(name, ok, detail=''):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def main():
    conn = sqlite3.connect('faq_dev.db')
    cur = conn.cursor()

    # ── 0a. 幂等补齐测试专员（保证脚本可重复运行） ──
    for uid, name in [
        (SPECIALIST_3, '孙专员'), (SPECIALIST_4, '周专员'), (SPECIALIST_5, '吴专员'),
    ]:
        cur.execute(
            "INSERT OR IGNORE INTO users "
            "(id, openid, login_username, real_name, recognition_role, "
            " total_score, correct_count, total_count, recognition_score, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'specialist', 0, 0, 0, 0, datetime('now'), datetime('now'))",
            (uid, 'test_' + uid, uid, name),
        )
    conn.commit()

    # ── 0b. 清理当月测试评分数据（含本次新增的补位专员评分） ──
    cur.execute(
        "DELETE FROM recognition_surveys WHERE survey_month = ? "
        "AND rater_id IN ('test-sales-001','test-sales-002')",
        (MONTH,),
    )
    conn.commit()
    conn.close()

    client = httpx.Client(base_url=BASE, timeout=30, trust_env=False)

    def h(uid):
        return {"Authorization": f"Bearer {create_access_token(uid)}"}

    # ── 1. 销售查看本月评分状态（全部专员列表） ──
    r = client.get('/api/recognition/surveys/status', headers=h(SALES_1))
    body = r.json()
    data = body.get('data', {})
    specialists = data.get('specialists') or []
    ids = [s.get('specialist_id') for s in specialists]
    ok = (body.get('code') == 0 and SPECIALIST_1 in ids and SPECIALIST_2 in ids
          and SPECIALIST_3 in ids and 'rated_count' in data and data.get('max_specialists') == 4
          and not any(s.get('scores') for s in specialists))
    log('销售查看本月评分状态(全部专员+名额字段)', ok,
        f"specialists={ids} rated_count={data.get('rated_count')} max={data.get('max_specialists')} month={data.get('survey_month')}")

    # ── 2. 销售为两位专员提交评分 ──
    scores_s1 = {"target_id": SPECIALIST_1, "survey_month": MONTH,
                 "score_efficiency": 5, "score_response": 4,
                 "score_training": 3, "score_communication": 5}
    r = client.post('/api/recognition/surveys', headers=h(SALES_1), json=scores_s1)
    ok = r.json().get('code') == 0
    log('销售为专员A提交评分', ok, f"http={r.status_code} msg={r.json().get('message')}")

    # 提交含 0(N/A) 的评分，验证后端归一化为 NULL
    scores_s2 = {"target_id": SPECIALIST_2, "survey_month": MONTH,
                 "score_efficiency": 4, "score_response": 0,
                 "score_training": 4, "score_communication": 4}
    r = client.post('/api/recognition/surveys', headers=h(SALES_1), json=scores_s2)
    ok = r.json().get('code') == 0
    log('销售为专员B提交评分(含0=N/A)', ok, f"http={r.status_code} msg={r.json().get('message')}")

    # ── 3. 重复提交校验 ──
    r = client.post('/api/recognition/surveys', headers=h(SALES_1), json=scores_s1)
    body = r.json()
    ok = body.get('code') == 1 and '已提交' in (body.get('message') or '')
    log('同销售同专员同月重复提交被拒绝', ok, f"msg={body.get('message')}")

    # ── 4a. 非专员目标评分被拒 ──
    bad = {"target_id": DISTRIBUTOR, "survey_month": MONTH,
           "score_efficiency": 5, "score_response": 5,
           "score_training": 5, "score_communication": 5}
    r = client.post('/api/recognition/surveys', headers=h(SALES_2), json=bad)
    body = r.json()
    ok = body.get('code') == 1 and '专员' in (body.get('message') or '')
    log('非专员目标评分被拒绝', ok, f"msg={body.get('message')}")

    # ── 4b. 目标不存在被拒 ──
    bad = {"target_id": 'nonexistent-user', "survey_month": MONTH,
           "score_efficiency": 5, "score_response": 5,
           "score_training": 5, "score_communication": 5}
    r = client.post('/api/recognition/surveys', headers=h(SALES_2), json=bad)
    body = r.json()
    ok = body.get('code') == 1
    log('目标不存在被拒绝', ok, f"msg={body.get('message')}")

    # ── 5. 超过每月4位上限被拒 ──
    rater2_targets = [SPECIALIST_1, SPECIALIST_3, SPECIALIST_4, SPECIALIST_5]
    for i, tid in enumerate(rater2_targets):
        payload = {"target_id": tid, "survey_month": MONTH,
                   "score_efficiency": 4, "score_response": 4,
                   "score_training": 4, "score_communication": 4}
        r = client.post('/api/recognition/surveys', headers=h(SALES_2), json=payload)
        ok = r.json().get('code') == 0
        log(f'销售2为第{i+1}位专员提交评分', ok, f"target={tid} msg={r.json().get('message')}")
    # 第5位被拒
    r = client.post('/api/recognition/surveys',
                    headers=h(SALES_2),
                    json={"target_id": SPECIALIST_2, "survey_month": MONTH,
                          "score_efficiency": 4, "score_response": 4,
                          "score_training": 4, "score_communication": 4})
    body = r.json()
    ok = body.get('code') == 1 and '最多' in (body.get('message') or '')
    log('超过4位上限被拒绝', ok, f"msg={body.get('message')}")

    # ── 6. 专员查看匿名汇总（不含提交人） ──
    r = client.get('/api/recognition/surveys/results', headers=h(SPECIALIST_1), params={'month': MONTH})
    body = r.json()
    data = body.get('data') or []
    mine = [d for d in data if d.get('target_id') == SPECIALIST_1]
    ok = len(mine) > 0 and 'rater_id' not in mine[0] and 'rater_name' not in mine[0]
    detail = f"target={mine[0]['target_name']} avg={mine[0].get('avg_scores')} median={mine[0].get('median_score')} raters={mine[0].get('rater_count')}" if mine else '未找到'
    log('专员端查看匿名汇总(不含提交人)', ok, detail)

    # ── 7. 经理查看明细分（含提交人） ──
    r = client.get('/api/recognition/surveys/details', headers=h(MANAGER), params={'month': MONTH})
    body = r.json()
    detail_list = body.get('data') or []
    s1_rows = [d for d in detail_list if d.get('rater_id') == SALES_1]
    ok = len(s1_rows) == 2 and all(d.get('rater_name') for d in s1_rows) and all(d.get('target_name') for d in s1_rows)
    log('经理端查看明细分(含提交人)', ok,
        f"rows={[(d['rater_name'], d['target_name'], d['scores']) for d in s1_rows]}")

    # ── 8. 非销售角色访问评分接口被拒 ──
    r = client.get('/api/recognition/surveys/status', headers=h(SPECIALIST_1))
    ok = r.status_code == 403
    log('专员访问销售评分接口被拒绝(403)', ok, f"http={r.status_code}")

    # ── 汇总 ──
    failed = [x for x in results if not x[1]]
    print('=' * 60)
    if failed:
        print(f'FAILED: {len(failed)}/{len(results)}')
        for name, ok, detail in failed:
            print(f'  - {name}: {detail}')
        sys.exit(1)
    print(f'ALL {len(results)} TESTS PASSED')


if __name__ == '__main__':
    main()