const STORAGE_PREFIX = 'weeklyQuizSeen:';

function normalizeUserId(userId) {
  return String(userId || 'guest').trim() || 'guest';
}

function buildWeeklyQuizSeenKey(userId) {
  return `${STORAGE_PREFIX}${normalizeUserId(userId)}`;
}

function shouldShowWeeklyQuizBadge(quizDate, seenQuizDate) {
  const current = String(quizDate || '').trim();
  if (!current) return false;
  return current !== String(seenQuizDate || '').trim();
}

module.exports = {
  buildWeeklyQuizSeenKey,
  shouldShowWeeklyQuizBadge
};
