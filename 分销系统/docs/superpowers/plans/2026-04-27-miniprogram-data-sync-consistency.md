# Mini Program Data Sync Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make profile, avatar, score, study record, ranking, and redemption data converge across devices by treating backend data as the source of truth and refreshing cached client state after mutations.

**Architecture:** Introduce a small app-level sync layer for dirty-scope tracking and current-user refresh, then wire mutation points to mark affected scopes and refresh profile cache. Keep the mini-program non-realtime, but guarantee that returning to key pages re-fetches authoritative backend state.

**Tech Stack:** WeChat Mini Program, `wx.cloud.callContainer`, local storage, Node-based regression tests

---

### Task 1: Add app-level sync helpers

**Files:**
- Create: `faq-miniprogram/tests/data-sync-state.test.js`
- Modify: `faq-miniprogram/app.js`

- [ ] Add failing tests for dirty-scope bookkeeping and profile cache refresh helpers.
- [ ] Run the new test and confirm it fails before implementation.
- [ ] Add `markDataDirty`, `consumeDataDirty`, `peekDataDirty`, and `refreshCurrentUserProfile` to `app.js`.
- [ ] Re-run the new test and make it pass.

### Task 2: Normalize user profile writes

**Files:**
- Modify: `faq-miniprogram/pages/login/login.js`
- Modify: `faq-miniprogram/pages/register/register.js`
- Modify: `faq-miniprogram/pages/profile-edit/profile-edit.js`

- [ ] Route all successful user/profile writes through `app.setUserInfo(...)`.
- [ ] Make avatar upload save profile data to backend immediately after upload success.
- [ ] Mark profile-related dirty scopes after profile changes.
- [ ] Add or extend tests covering avatar upload + auto-save behavior.

### Task 3: Mark learning and energy mutations as dirty

**Files:**
- Modify: `faq-miniprogram/pages/quiz/quiz.js`
- Modify: `faq-miniprogram/pages/question-list/question-list.js`
- Modify: `faq-miniprogram/pages/energy-mall/index.js`

- [ ] After daily quiz submit, mark study/rank/profile scopes dirty.
- [ ] After practice answer submit, mark study/rank/profile scopes dirty.
- [ ] After redemption success, mark profile/energy/redeem scopes dirty and refresh summary cache if needed.
- [ ] Add minimal regression coverage for mutation-to-dirty-scope behavior where practical.

### Task 4: Refresh key pages from authoritative data

**Files:**
- Modify: `faq-miniprogram/pages/wode_User_Profile_Green/wode_User_Profile_Green.js`
- Modify: `faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.js`
- Modify: `faq-miniprogram/pages/studyRecord/index.js`
- Modify: `faq-miniprogram/pages/leaderboard/leaderboard.js`
- Modify: `faq-miniprogram/pages/redeem-record/index.js`
- Modify: `faq-miniprogram/pages/energy-mall/index.js`

- [ ] On `onShow`, consume relevant dirty scopes and refresh current user profile before page-specific loads where the page displays profile-derived data.
- [ ] Keep existing remote fetches, but ensure cached `userInfo` no longer wins over backend truth.
- [ ] Re-run page-level regression tests plus syntax checks.

### Task 5: Verify consistency behavior

**Files:**
- Test: `faq-miniprogram/tests/data-sync-state.test.js`
- Test: `faq-miniprogram/tests/profile-edit-avatar-picker.test.js`
- Test: `faq-miniprogram/tests/avatar-upload.test.js`

- [ ] Run all new/affected Node tests.
- [ ] Run `node --check` for each modified page/app script.
- [ ] Summarize what now syncs after “return to page / reopen page” and what still requires full realtime infrastructure.
