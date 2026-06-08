# 施能量商品后台与权威兑换设计

## 目标

将施能量商城的商品信息、上下架状态和兑换规则从小程序前端迁移到后端数据库，由后端作为唯一权威来源；同时新增一个独立的 `admin` Web 页面，仅供管理员维护商品，小程序用户端只读取已上架商品并提交 `product_id` 完成兑换。

## 非目标

- 本次不实现复杂的发货、库存、物流和审批流。
- 本次不实现多角色权限系统。
- 本次不把管理功能塞进小程序。

## 现状问题

- 小程序 `faq-miniprogram/pages/energy-mall/index.js` 中硬编码了完整商品列表、商品名称和积分价格。
- 后端 `faq-backend/app/api/v1/energy.py` 当前直接信任前端传入的 `product_id / product_name / cost / status`。
- 这意味着只要用户改请求，就可以伪造价格、商品名和状态。

## 总体方案

采用后端一体化方案：

1. 新增数据库商品表，保存商品名称、积分、分类、描述、图片、排序、上下架状态等字段。
2. 后端新增面向小程序的商品查询接口，仅返回已上架商品。
3. 后端重写兑换创建逻辑，只接受 `product_id` 和客户端幂等键，商品名称、价格、状态全部由后端决定。
4. 后端新增独立 `admin` 登录与商品管理接口。
5. 在 FastAPI 下挂载一个独立 `admin` 静态网页，管理员通过浏览器访问，不暴露给小程序普通用户。
6. 小程序商城页改为从后端拉商品列表并展示，不再以内置常量作为权威数据。

## 数据模型

新增 `energy_products` 表，字段建议如下：

- `id`：UUID 主键
- `product_id`：业务商品编号，唯一，对外暴露给小程序
- `name`：商品名称
- `description`：商品描述
- `category`：商品分类
- `cost`：兑换所需能量
- `image_url`：商品图片地址
- `badge`：角标文案，可选
- `tag`：标签文案，可选
- `art_label`：前端占位展示文案，可选
- `art_class`：前端占位样式类名，可选
- `sort_order`：排序值
- `is_featured`：是否热门推荐
- `is_active`：是否上架
- `created_at`
- `updated_at`

现有 `energy_redemption_records` 表保留，但创建记录时不再相信前端传入的商品元数据，改为从 `energy_products` 查询并写入。

## 小程序接口设计

新增接口：

- `GET /api/energy/products`
  - 仅返回已上架商品
  - 返回分组所需字段和推荐商品字段
  - 后端可直接按积分区间或排序返回，小程序不再维护硬编码商品库

调整接口：

- `POST /api/energy/redemptions`
  - 请求体改为只包含：
    - `client_record_id`
    - `product_id`
  - 后端执行：
    - 校验商品存在
    - 校验商品已上架
    - 校验该用户可用能量是否足够
    - 校验幂等记录是否已存在
    - 用数据库商品信息写入兑换记录
    - 返回最新汇总

兼容接口：

- `POST /api/energy/redemptions/sync`
  - 保留用于兼容旧客户端
  - 仅接受已存在的旧格式
  - 对新版本小程序不再依赖本地兑换历史同步

## Admin 后台设计

### 登录

先使用环境变量中的单管理员账号密码，不引入完整后台用户体系。

新增环境变量：

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_SECRET_KEY` 或复用现有 JWT 体系并加单独的 admin claim

新增接口：

- `POST /api/admin/auth/login`
- `GET /api/admin/products`
- `POST /api/admin/products`
- `PUT /api/admin/products/{product_id}`
- `POST /api/admin/products/{product_id}/toggle`

所有 `/api/admin/*` 接口都需要管理员 token。

### 页面

在后端静态资源下新增 `/admin/` 页面，包含：

- 管理员登录页
- 商品列表页
- 商品新增/编辑弹窗或表单
- 上下架开关
- 排序和推荐位编辑

普通小程序用户不会看到该页面，因为它不在小程序路由里，只存在于浏览器访问路径中。

## 后端权威规则

兑换时后端必须保证：

- 只认数据库中的商品，不认前端传来的商品名称和价格
- 只允许兑换已上架商品
- 使用当前数据库中的 `cost` 进行余额校验
- `status` 初始值由后端统一写为 `pending`
- 幂等键重复提交时返回已有记录而不是重复创建

## 小程序改造范围

需要改动 `faq-miniprogram/pages/energy-mall/index.js`：

- 删除本地硬编码商品清单的权威角色
- 页面加载时请求 `/api/energy/products`
- 用接口返回结果渲染推荐商品和商品分组
- 兑换时只提交 `client_record_id` 和 `product_id`
- “可兑换/不可兑换”状态仍可在前端根据后端返回的 `cost` 与当前 `availableEnergy` 做 UI 展示，但不作为安全校验依据

## 后端改造范围

需要改动：

- `faq-backend/app/models/`：新增商品模型
- `faq-backend/migrations/versions/`：新增商品表迁移
- `faq-backend/app/api/v1/energy.py`：新增商品接口并收紧兑换接口
- `faq-backend/app/api/v1/router.py`：注册 admin 路由
- `faq-backend/app/main.py`：挂 admin 静态入口
- `faq-backend/app/static/`：新增 admin 页面资源

## 初始化策略

首版商品数据通过脚本或数据迁移导入，来源于当前小程序里的商品清单。导入完成后，以数据库为准；后续增删改通过 admin 页面完成。

## 错误处理

小程序侧：

- 商品加载失败时提示“商城加载失败”
- 兑换失败时显示后端返回的明确业务错误，如“商品已下架”或“能量不足”

后端侧：

- 未找到商品：`404`
- 商品未上架：`400`
- 能量不足：`400`
- 重复幂等请求：返回已有记录和最新汇总
- admin 未授权：`401`

## 测试策略

新增后端测试覆盖：

- 查询商品列表仅返回上架商品
- 兑换接口忽略前端伪造的名称和价格
- 下架商品不可兑换
- 能量不足不可兑换
- 幂等键重复时不会重复创建记录
- admin 登录和商品 CRUD 的基本接口测试

小程序侧至少手工验证：

- 商城列表展示
- 热门推荐展示
- 兑换成功
- 能量不足提示
- 商品下架后用户端不再显示

## 交付边界

第一阶段交付：

- 商品表
- 商品初始化导入
- 小程序商品接口
- 后端权威兑换
- 独立 admin 网页
- 基础管理员登录

第二阶段可选扩展：

- 多管理员
- 商品图片上传
- 兑换审核流
- 发货/核销流程
