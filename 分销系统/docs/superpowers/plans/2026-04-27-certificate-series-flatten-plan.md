# Certificate Series Flatten Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去掉证书查询页第三层分类展示，直接按证书类型展示合并后的产品系列，并在详情页汇总所有来源分类的详情。

**Architecture:** 在证书查询页前端新增一个聚合 helper，负责把多个分类下的产品系列按名称合并，并把来源分类数组挂到聚合结果上。页面逻辑改为证书类型选中后直接加载聚合产品系列，详情页再按来源分类逐个拉详情并合并展示。

**Tech Stack:** 微信小程序页面脚本、现有证书 REST API、Node.js 断言脚本。

---

### Task 1: 证书聚合 helper

**Files:**
- Create: `faq-miniprogram/pages/certificate/aggregation.js`
- Test: `faq-miniprogram/tests/certificate-aggregation.test.js`

- [ ] 写失败测试，覆盖“同名产品系列跨分类合并并累加 count”
- [ ] 运行 `node faq-miniprogram/tests/certificate-aggregation.test.js`，确认先失败
- [ ] 实现最小 helper
- [ ] 再跑同一条命令，确认转绿

### Task 2: 证书页状态机切换到扁平产品系列

**Files:**
- Modify: `faq-miniprogram/pages/certificate/index.js`
- Modify: `faq-miniprogram/pages/certificate/index.wxml`

- [ ] 把证书类型点击后的行为改成直接加载聚合产品系列
- [ ] 移除单独的分类页展示和返回链路
- [ ] 更新面包屑、标题、副标题

### Task 3: 详情页汇总所有来源分类

**Files:**
- Modify: `faq-miniprogram/pages/certificate/index.js`
- Test: `faq-miniprogram/tests/certificate-aggregation.test.js`

- [ ] 为聚合后的产品系列保存来源分类数组
- [ ] 点产品系列时按所有来源分类并发拉详情并合并展示
- [ ] 跑 `node faq-miniprogram/tests/certificate-aggregation.test.js`
- [ ] 跑 `node --check faq-miniprogram/pages/certificate/index.js`
