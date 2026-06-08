function normalizeImageUrl(value) {
  return String(value || '').trim();
}

function decorateProductForMall(product, availableEnergy, isGuestMode) {
  const cost = Math.max(0, Number(product.cost) || 0);
  const displayImageUrl = normalizeImageUrl(product.imageUrl || product.image_url);
  let actionText = '兑换';
  let actionState = 'ready';

  if (isGuestMode) {
    actionText = '登录';
    actionState = 'guest';
  } else if (availableEnergy < cost) {
    actionText = '不足';
    actionState = 'locked';
  }

  return {
    ...product,
    cost,
    displayImageUrl,
    hasImage: !!displayImageUrl,
    actionText,
    actionState
  };
}

module.exports = {
  decorateProductForMall
};
