# AI Chat Session Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让智能问答页在重新打开后恢复当前用户的本地对话记录，并在“一键清屏”时同步删除缓存。

**Architecture:** 把聊天缓存逻辑抽到独立 helper，负责生成用户隔离的缓存 key、序列化/反序列化页面快照，以及把流式中的消息降级成可恢复状态。页面本身只负责在加载时恢复、在关键状态变化后写回、在清屏时删除。

**Tech Stack:** 微信小程序页面脚本、`wx` 本地存储、Node.js 内置测试运行器。

---

### Task 1: 聊天缓存 helper

**Files:**
- Create: `faq-miniprogram/pages/zhinengwenda_AI_Assistant_Green/chatSessionCache.js`
- Test: `faq-miniprogram/tests/ai-chat-session-cache.test.js`

- [ ] **Step 1: Write the failing test**

```js
test('serialize/deserialize keeps stable messages and clears streaming state', () => {
  const state = {
    messages: [
      { id: 'msg_1', type: 'user', text: '你好' },
      { id: 'msg_2', type: 'ai', text: '处理中', streaming: true, statusIndicator: true }
    ],
    inputValue: '草稿',
    guidePathIndices: [1, 2],
    selectedGuideLeafId: 'leaf-1',
    lastMsgId: 'msg_2'
  };

  const payload = serializeChatSessionState(state);
  const restored = deserializeChatSessionState(payload);

  assert.equal(restored.messages[1].streaming, false);
  assert.equal(restored.messages[1].statusIndicator, false);
  assert.deepEqual(restored.guidePathIndices, [1, 2]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test faq-miniprogram/tests/ai-chat-session-cache.test.js`
Expected: FAIL with module/function missing

- [ ] **Step 3: Write minimal implementation**

```js
function buildChatSessionStorageKey(userId) {
  return `aiChatSession:${String(userId || 'guest').trim() || 'guest'}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test faq-miniprogram/tests/ai-chat-session-cache.test.js`
Expected: PASS

### Task 2: 页面接入缓存恢复和清除

**Files:**
- Modify: `faq-miniprogram/pages/zhinengwenda_AI_Assistant_Green/zhinengwenda_AI_Assistant_Green.js`
- Test: `faq-miniprogram/tests/ai-chat-session-cache.test.js`

- [ ] **Step 1: Write the failing test**

```js
test('clear payload resets persisted state to initial snapshot', () => {
  const payload = serializeChatSessionState({
    messages: [{ id: 'msg_0', type: 'ai', text: '欢迎' }],
    inputValue: '',
    guidePathIndices: [],
    selectedGuideLeafId: '',
    lastMsgId: 'msg_0'
  });

  const restored = deserializeChatSessionState(payload);
  assert.equal(restored.lastMsgId, 'msg_0');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test faq-miniprogram/tests/ai-chat-session-cache.test.js`
Expected: FAIL because helper shape is incomplete

- [ ] **Step 3: Write minimal implementation**

```js
restoreConversationCache() { ... }
persistConversationCache() { ... }
clearConversationCache() { ... }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test faq-miniprogram/tests/ai-chat-session-cache.test.js`
Expected: PASS

### Task 3: 页面行为复核

**Files:**
- Modify: `faq-miniprogram/pages/zhinengwenda_AI_Assistant_Green/zhinengwenda_AI_Assistant_Green.js`

- [ ] **Step 1: Wire lifecycle and state writes**

```js
await this.restoreConversationCache();
this.persistConversationCache();
this.clearConversationCache();
```

- [ ] **Step 2: Run targeted verification**

Run: `node --test faq-miniprogram/tests/ai-chat-session-cache.test.js`
Expected: PASS

Run: manually reopen the mini-program chat page and verify history remains; tap clear-screen and verify history disappears after reopening.
Expected: history restores before clear and is gone after clear
