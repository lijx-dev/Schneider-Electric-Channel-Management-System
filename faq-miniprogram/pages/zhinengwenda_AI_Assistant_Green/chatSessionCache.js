const STORAGE_PREFIX = 'aiChatSession:';

function normalizeUserId(userId = '') {
  return String(userId || '').trim() || 'guest';
}

function buildChatSessionStorageKey(userId = '') {
  return `${STORAGE_PREFIX}${normalizeUserId(userId)}`;
}

function sanitizeMessage(message = {}) {
  const nextMessage = {
    ...message,
    id: String(message.id || ''),
    type: String(message.type || ''),
    text: String(message.text || ''),
    streaming: false,
    statusIndicator: false,
    thinkingStatus: false
  };

  delete nextMessage.displayNodes;
  return nextMessage;
}

function sanitizeGuidePathIndices(guidePathIndices = []) {
  if (!Array.isArray(guidePathIndices)) {
    return [];
  }

  return guidePathIndices
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value) && value >= 0);
}

function serializeChatSessionState(state = {}) {
  return JSON.stringify({
    messages: Array.isArray(state.messages) ? state.messages.map(sanitizeMessage) : [],
    inputValue: String(state.inputValue || ''),
    guidePathIndices: sanitizeGuidePathIndices(state.guidePathIndices),
    selectedGuideLeafId: String(state.selectedGuideLeafId || ''),
    lastMsgId: String(state.lastMsgId || '')
  });
}

function deserializeChatSessionState(rawValue) {
  if (!rawValue || typeof rawValue !== 'string') {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }

    if (!Array.isArray(parsed.messages)) {
      return null;
    }

    return {
      messages: parsed.messages.map(sanitizeMessage),
      inputValue: String(parsed.inputValue || ''),
      guidePathIndices: sanitizeGuidePathIndices(parsed.guidePathIndices),
      selectedGuideLeafId: String(parsed.selectedGuideLeafId || ''),
      lastMsgId: String(parsed.lastMsgId || '')
    };
  } catch (error) {
    return null;
  }
}

module.exports = {
  buildChatSessionStorageKey,
  serializeChatSessionState,
  deserializeChatSessionState
};
