# Knowledge Items Design

## Goal

Add a "Knowledge Set" module in the third feature-card position on the mini program home page. The feature lets users save question explanations as standalone knowledge points while answering weekly quiz or question-bank practice questions.

The knowledge set must not behave like a wrong-answer notebook. It stores and displays only explanation content. The knowledge list page must not show the original question, options, submitted answer, or correct answer.

## Scope

Included:

- Add a third home feature card named "知识集".
- Add a knowledge set mini program page.
- Add an "加入知识集" action in explanation panels after an explanation is visible.
- Persist saved explanations on the backend so they sync across devices.
- Avoid duplicate saved items for the same user and question.
- Allow users to remove saved knowledge points.

Excluded:

- Folder/tag management inside the knowledge set.
- Search, sorting controls, or manual editing.
- Saving full question content.
- Rebuilding the old mistakes table.
- Admin management for knowledge items.

## Backend Design

Create a new model named `KnowledgeItem` in a new table named `knowledge_items`.

Fields:

- `id`: integer primary key.
- `user_id`: foreign key to `users.id`.
- `question_id`: foreign key to `questions.id`.
- `explanation`: text snapshot copied from `questions.explanation` when saved.
- `source`: short string, expected values `daily` or `bank`.
- `created_at` and `updated_at`: inherited timestamp fields.

Constraints and indexes:

- Unique constraint on `(user_id, question_id)` to prevent duplicate saves.
- Index on `user_id` for listing a user's saved knowledge points.
- Cascade delete when a user or question is removed.

Saving uses a snapshot instead of reading live question explanations every time. This keeps the knowledge item stable after the user saves it and also lets the list page avoid returning question details.

## API Design

Add a new router module, for example `app/api/v1/knowledge.py`, and register it in the v1 router.

Endpoints:

- `GET /api/knowledge`
  - Authenticates the current user.
  - Returns the current user's saved knowledge items ordered by newest first.
  - Response items include only `id`, `explanation`, `source`, and `created_at`.

- `POST /api/knowledge`
  - Body: `user_id`, `question_id`, `source`.
  - Verifies the caller is saving for themselves.
  - Loads the question and requires a non-empty `explanation`.
  - Creates a `KnowledgeItem` with the explanation snapshot.
  - If the same `(user_id, question_id)` already exists, returns the existing item with an `already_saved` flag.

- `DELETE /api/knowledge/{item_id}`
  - Deletes only if the item belongs to the current user.
  - Returns success for a deleted item; returns 404 if not found.

The API never returns question content, options, answer, or selected answer.

## Mini Program Design

### Home Entry

Update the home feature card row from two cards to three cards:

1. 每周答题
2. 题库练习
3. 知识集

The third card navigates to `/pages/knowledge/index`. Its subtitle should make the feature clear, for example "收藏解析知识点".

The layout should keep the current soft green card style but reduce card width and spacing so three cards fit cleanly on mobile. If the text becomes tight, use shorter copy rather than shrinking text aggressively.

### Save Action

Add a save action in both answer flows:

- Weekly quiz page: `pages/quiz/quiz`.
- Question-bank practice page: `pages/question-list/question-list`.

The button appears inside or near the explanation block only when an explanation exists and is visible. The button sends `question_id` and `source` to `POST /api/knowledge`.

Button states:

- Default: "加入知识集".
- After success: "已加入".
- If backend reports it already exists: "已加入".
- If no explanation exists: no button is shown.

The button must not save the complete question locally or send question content to the backend.

### Knowledge Page

Add `pages/knowledge/index`.

The page lists saved explanations only. Each item displays:

- Explanation text.
- Save time as secondary metadata.
- A delete action.

Empty state:

- Title: "还没有知识点".
- Copy: "答题后可以把解析加入知识集。"

Loading and error states should match the existing simple page patterns used by study and redemption record pages.

## Data Flow

1. User answers a quiz or practice question.
2. Backend submit API returns `explanation`.
3. Mini program displays the explanation and the save action.
4. User taps "加入知识集".
5. Mini program calls `POST /api/knowledge` with `user_id`, `question_id`, and `source`.
6. Backend copies `Question.explanation` into `KnowledgeItem.explanation`.
7. Knowledge page fetches `GET /api/knowledge` and renders only saved explanation text.

## Error Handling

- If the question does not exist, return 404.
- If the question has no explanation, return 400 with a clear message.
- If a duplicate save is attempted, return the existing item with `already_saved: true`.
- If the user is not logged in, the mini program should use the existing `app.requireLogin()` guard.
- If delete fails, show a toast and keep the item visible.

## Testing Plan

Backend:

- Model migration creates `knowledge_items` with expected constraints.
- `POST /api/knowledge` saves an explanation snapshot.
- Duplicate save returns `already_saved: true` and does not create another row.
- `GET /api/knowledge` returns only explanation-oriented fields.
- `DELETE /api/knowledge/{item_id}` enforces ownership.

Mini program:

- Home renders three feature cards without overlapping text.
- Save button appears only after an explanation is visible.
- Save success changes the button state to "已加入".
- Knowledge page shows only explanation content and not question content.
- Empty state appears for users without saved items.

## Implementation Notes

The current repository contains unrelated uncommitted changes in the home page and backend scripts. Implementation should avoid reverting those changes and should touch only the files required for this feature.

Some existing mini program source files display mojibake in the terminal but are used by the project as-is. Edits should preserve the existing encoding behavior and avoid broad text rewrites.
