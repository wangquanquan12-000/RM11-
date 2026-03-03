# Paid Live 设置免费预览时间

| 项目 | 信息 |
|------|------|
| JIRA 链接 | https://jira.corp.5miles.io/browse/FAM-10569 |
| 产品负责人 | jiali |
| 测试负责人 | lingling |
| 技术负责人 | liubingtong |
| 技术文档 | Paid Live Free Preview — 前后端接口对接文档 [GitHub] |
| 开发总结测试文档 | Paid Live Free Preview — QA 测试文档 |
| 预估时间 | — |

---

## 一、背景 / 目的

在付费前先预览一小段时间，以提升用户对直播内容的理解和付费意愿。

---

## 二、原型图 / 设计图

- Paid Live 设置页 – 新增 Preview 设置入口
- Preview 倒计时展示，Preview 结束后的付费解锁页

（见最新 Paid Live + Preview 相关设计图）

---

## 三、需求描述

### 模块 1：主播端 – Paid Live 弹窗新增 Free Preview 设置

主播在开播前或直播设置中点开 Paid Live 弹窗。

#### 1. Paid Live 开关关闭时

- 第 2 点文案修改为：**You can set a free access level and preview duration for viewers.**

#### 2. 开关打开后

1. 原「Set Free Access」与「Preview」入口合并为：**Level Access & Preview**
2. 点击该入口，从右向左打开总设置弹窗：**Level Access & Preview 弹窗**
3. **Level Access & Preview 入口展示规则：**
   - 没设置 level，没设置 preview 时间：`Level Access · Preview`  
     - 注意：`·` 为显示清楚加粗（若效果不好可改为图形，由设计提供）
   - 设置了 level，没设置 preview：`Level {{level}}+ Access`
   - 没设置 level，设置了 preview：`{{Duration}} Preview`
   - 设置了 level，设置了 preview：`Level {{X}}+ · {{Duration}} Preview`  
     - 如：`Level 10+ · 10s Preview`
4. **其他交互不变：**
   - 修改礼物、level access、preview 后，仍需点击 **Done** 才算保存
5. **修改 level 和 preview 时间算不算次数？** 不算

#### 3. 开播后保存逻辑

- 保存 Paid Live 的整体设置，下次进入直播设置页面时使用上次的设置
- Preview 的缓存逻辑：同门票礼物和 level

---

### Level Access & Preview 弹窗

1. **展示两个选项：**

   **（1）Level Access**
   - 描述：Viewers at or above the selected level can enter without a gift.
   - Not Set 时：Level Access 后展示「空」
   - 设置了 level 后：Level Access 后展示 `Level {{level}}+`（如 Level 10+）
   - 点击这一行，打开 **Level Access 弹窗**（原 Set Free Access 弹窗）

   **（2）Preview**
   - 描述：Viewers can preview for a short time before unlocking.
   - 未设置时：Preview 后展示「空」
   - 设置了 preview 后：Preview 后展示主播所选的预览时长（如 `10s`）
   - 点击这一行，打开 **Preview 弹窗**

2. 点击返回 → 回到 Paid Live 弹窗
3. 点击弹窗外 → 无响应

---

### Level Access 弹窗（原 Set Free Access 弹窗）

1. 修改标题为：**Level Access**
2. 修改描述为：Set a minimum level to let viewers enter the Live without a gift.
3. 其他内容、设置和编辑时的交互同之前
4. **点击 Confirm 后：**
   - 按钮 loading
   - 成功 → 返回前一级页面，Level Access & Preview 弹窗中展示最新设置项
   - 失败 → 在当前页面 toast 报错（参考「六、toast 报错: 通用交互定义」）
5. 点左上角的返回 icon → 不做任何修改，返回前一级页面
6. 点弹窗外 → 无响应

---

### Preview 弹窗

1. **标题：** Preview
2. **描述：** Let viewers preview the live for a short time before unlocking with a gift.
3. **选项：**
   - Not Set
   - 5s
   - 10s
   - 30s
   - 1min
   - 3min
   - 用户可以上下滑动选项区，选择自己需要的预览时间
4. 没设置过：默认选中 Not Set；设置过再进入编辑：默认选中之前的设置项
5. **点击 Confirm 按钮后：**
   - 即确认选择，按钮 loading
   - 成功 → 返回前一级页面，Level Access & Preview 弹窗中展示已选择的时间
   - 失败 → 在当前页面 toast 报错（参考「六、toast 报错: 通用交互定义」）
6. 点左上角的返回 icon → 不做任何修改，返回前一级页面
7. 点弹窗外 → 无响应
8. **说明：**
   - Preview 仅对需要送礼物解锁的用户生效，可预览一段时间
   - 不影响 admin / mod / 高 Level 用户的进入规则

---

### 模块 2：Viewer 进入直播间

Viewer 尝试进入 Paid Live 时，按以下优先级判断：

1. **部分身份可直接进入直播间（原逻辑）**
   - 群主
   - admin
   - mod
   - 该主播的 performer mod（若主播是 performer）

2. **若主播设置了 Level Access（原逻辑）**
   - 大于等于 Level Access 要求的用户，看到无需送礼页面，然后自动/手动进入
   - 若没设置，则跳过

3. **不是 1 中身份，且不满足 level access 的付费解锁用户**
   - 若主播**未开启** Preview → 直接进入付费解锁页面（原逻辑）
   - 若主播**已开启** Preview → 进入 Preview 页面（见模块 3）

---

### 模块 3：直播预览页面 Preview

#### 1. 展示直播间的画面和部分功能

| 区域 | 说明 |
|------|------|
| **顶部** | 左侧：主播头像和名字（不展示钻石，无论主播是否打开开关）；右侧：X icon（点击关闭预览页面） |
| **Lovense** | 若连了 lovense，展示 lovense 区域；无论是否在播放，都只展示 icon |
| **直播画面** | 与正常直播一致（不遮挡/不打码） |
| **整体** | 除 X icon 外，以上内容被遮罩盖住，仅观看不可操作 |

#### 2. 「你正在预览」提醒

- 图标：眼睛 icon
- 文案：You're in Free Preview Mode

#### 3. 倒计时展示

- 以数字形式展示剩余预览时间：**mm:ss**（如：01:29，00:01）
- 从主播设置的 Preview 时长开始倒计时，每秒刷新
- 倒计时剩余 3s 时，数字变红
- 倒计时到 00:00 时，Preview 结束 → 变为付费解锁页面（直播画面被完全遮住）
  - 在送礼物提醒上方新增一句：**Free Preview Ended**（文案待校验）

#### 4. 直播标题

- 若有标题：展示到倒计时下方，全部展示
- 若无标题：不展示该区域

#### 5. Unlock Live 按钮

- 按钮文案：`Unlock Live (门票礼物 icon 及金额)`  
  如：`Unlock Live (🌹 10 Coins)`
- Preview 期间始终可点
- 点击后立刻送礼
- 送礼成功 → 解锁直播，跳转到正常直播间
- 送礼失败 → toast 提示失败原因
  - 余额不足：toast 提示的同时弹出充值弹窗
  - 其他错误：仅 toast 提醒

#### 6. Preview 期间用户主动退出

- 下次再次进入该直播：
  - 无论 Preview 时间是否用完，**不可再次预览**，直接进入付费解锁页面

#### 7. 用户进入过付费解锁页面未预览过，后来主播改成付费可预览

- 下次点开，可正常看到预览页面

---

### 模块 4：让主播知道有人在预览中

#### 1. 加入直播间的消息增加新状态

- 文案：`{{name}} is in preview`
- 与加入直播间的消息共用底部那一行位置，交互一致

#### 2. 贡献列表中增加预览用户展示

- 钻石列：展示预览的眼睛 icon 和剩余预览时间
- 剩余预览时间格式：`多长时间 left`  
  如：`1m 10s left`，`3s left`
- 倒计时实时更新
- 倒计时到 1 变成 0 后：不展示 0，直接从列表中移除该用户

#### 3. 排序规则

| 优先级 | 规则 |
|--------|------|
| 1 | 直播间的人优先：钻石多的优先，先进入的优先 |
| 2 | 预览中的人其次：先进入直播间的优先 |

#### 4. UI 更新（见设计图）

- 去掉 Diamonds 单词
- info icon 换位置
- 点击 info icon → 展示 Instructions 弹窗

#### 5. Instructions 弹窗（文案待校验）

**Diamonds**
- When you receive a gift in the group, its value is converted into Diamonds.
- The system then automatically converts your Diamonds into cash and adds it to your Income.

**Preview**
- The "👁️" icon means the user is currently previewing your Live.（icon 用设计图里的）
- 每场直播每个用户只能预览一次

---

## 四、其他

### 1. 用户停留预览页面 / 付费解锁页面，主播修改门票 / level / 预览

- 根据实时更新成新的设置

### 2. 主播在直播间修改免费预览时间

| 场景 | 行为 |
|------|------|
| 主播和被踢出的观众 | 提示文案不变 |
| 主播设置预览 + 观众**没**预览过该场直播 | 观众进入预览页面，后续流程同「自己点进预览页面」 |
| 主播设置预览 + 观众**已**预览过该场直播 | 观众进入付费解锁页面；无论上一次时间是否还有剩余，都算预览过，不可再预览 |

---

## 五、后台

- 直播数据中展示预览相关的设置记录

---

## 六、老版本兼容

| 主播版本 | 观众版本 | 行为 |
|----------|----------|------|
| 新版本（设置预览） | 老版本 | 观众直接进入付费解锁页面，不支持预览 |
| 新版本（未设置） / 老版本 | 老版本 | 等同于未设置预览时间，观众直接进入付费解锁页面 |
| 老版本 | 新版本 | 同上 |
| 老版本 | 老版本 | 同上 |

---

## 七、上线计划

- 开放给所有有 Paid Live 功能的人（normal、safe 主播）

---

## 八、数据埋点

1. **Preview 开启率：** 主播维度、场次维度
2. **解锁转化率对比：**  
   未开启 Preview vs 开启 Preview 的直播间：  
   解锁用户 / 进入过预览或付费页面的用户  
   - 再单独看：Preview 时长内解锁比例、Preview 后解锁比例
3. **Preview 时用户退出率**

---

*文档导出时间：2025-03-02*
