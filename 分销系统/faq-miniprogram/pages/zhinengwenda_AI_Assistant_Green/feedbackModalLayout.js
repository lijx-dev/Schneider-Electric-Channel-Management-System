function toPositiveNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) && numericValue > 0 ? numericValue : 0;
}

function calculateFeedbackModalOffset({
  windowHeight = 0,
  modalHeight = 0,
  keyboardHeight = 0,
  safeGap = 16
} = {}) {
  const safeWindowHeight = toPositiveNumber(windowHeight);
  const safeModalHeight = toPositiveNumber(modalHeight);
  const safeKeyboardHeight = toPositiveNumber(keyboardHeight);
  const safeSafeGap = toPositiveNumber(safeGap);

  if (!safeWindowHeight || !safeModalHeight || !safeKeyboardHeight) {
    return 0;
  }

  const centeredBottom = (safeWindowHeight + safeModalHeight) / 2;
  const keyboardTop = safeWindowHeight - safeKeyboardHeight;
  const requiredOffset = Math.ceil(centeredBottom + safeSafeGap - keyboardTop);
  const maxOffset = Math.max(
    0,
    Math.floor((safeWindowHeight - safeModalHeight) / 2 - safeSafeGap)
  );

  return Math.max(0, Math.min(requiredOffset, maxOffset));
}

module.exports = {
  calculateFeedbackModalOffset
};
