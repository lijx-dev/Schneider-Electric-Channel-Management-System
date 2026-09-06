/**
 * 学员姓名水印组件
 * 在页面内容上层平铺半透明斜体姓名水印（position:fixed 固定视口，防截屏追责）
 * 属性：name 水印文案（空串/未登录时不渲染）
 * 外部类：wm-class 供页面覆盖 bottom，避开各自固定底栏/输入区
 */
Component({
  externalClasses: ['wm-class'],

  properties: {
    name: {
      type: String,
      value: ''
    }
  },

  data: {
    rowList: [],
    colList: []
  },

  lifetimes: {
    attached() {
      let windowWidth = 375;
      let windowHeight = 667;
      try {
        if (typeof wx.getSystemInfoSync === 'function') {
          const sys = wx.getSystemInfoSync();
          windowWidth = Number(sys.windowWidth) || windowWidth;
          windowHeight = Number(sys.windowHeight) || windowHeight;
        }
      } catch (err) {
        // 取不到系统信息时使用默认值，不影响水印渲染
      }
      // 瓦片宽约 260px、行高约 120px，多算 1-2 行列保证斜排平铺覆盖完整
      const cols = Math.ceil(windowWidth / 260) + 2;
      const rows = Math.ceil(windowHeight / 120) + 1;
      this.setData({
        colList: Array.from({ length: cols }, (_, i) => i),
        rowList: Array.from({ length: rows }, (_, i) => i)
      });
    }
  }
});