/**
 * 学员姓名水印工具：构造水印文案（真实姓名 + 手机尾号4位）
 * 游客/未登录返回空串，页面据此隐藏水印
 */
function buildWatermarkText(app) {
  if (!app || !app.globalData) {
    return '';
  }
  const info =
    app.globalData.userInfo || wx.getStorageSync('userInfo') || null;
  if (!info) {
    return '';
  }
  // 真实姓名优先，缺失时用昵称兜底
  const name =
    String(info.real_name || '').trim() ||
    String(info.nickname || '').trim();
  if (!name) {
    return '';
  }
  // 手机号仅取后4位，非数字字符过滤；无手机号则只显示姓名
  const tail = String(info.phone || '').replace(/\D/g, '').slice(-4);
  return tail ? `${name} ${tail}` : name;
}

module.exports = { buildWatermarkText };