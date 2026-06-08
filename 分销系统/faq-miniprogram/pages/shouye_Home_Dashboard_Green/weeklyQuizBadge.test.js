const assert = require('node:assert/strict');
const {
  buildWeeklyQuizSeenKey,
  shouldShowWeeklyQuizBadge
} = require('./weeklyQuizBadge');

assert.equal(shouldShowWeeklyQuizBadge('2026-05-04', ''), true);
assert.equal(shouldShowWeeklyQuizBadge('2026-05-04', '2026-04-27'), true);
assert.equal(shouldShowWeeklyQuizBadge('2026-05-04', '2026-05-04'), false);
assert.equal(shouldShowWeeklyQuizBadge('', '2026-05-04'), false);
assert.equal(buildWeeklyQuizSeenKey(' user-1 '), 'weeklyQuizSeen:user-1');
assert.equal(buildWeeklyQuizSeenKey(''), 'weeklyQuizSeen:guest');
