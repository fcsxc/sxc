---
id: SPEC-SVC-007
title: 退款单创建返回字段
status: active
applies_to: orderflow.service
supersedes: ""
tags: 退款,接口,返回字段,服务
---

## 规则

1. `RefundService.create_refund(request)` 返回字典，至少包含：`order_id`、`reason`、`status`、`refund_cents`、`goods_refund_cents`、`shipping_refund_cents`、`clamped`。
2. `status` 在受理成功时为 `ACCEPTED`。
3. `requested_cents` 为空时 `refund_cents` 取可退上限；不为空时取 `min(requested_cents, 可退上限)`。
4. 未知订单号必须抛出 `KeyError`。

## 验收

- `create_refund` 的返回字段与本条一致。
- 传入超大 `requested_cents` 时 `refund_cents` 被截断到可退上限。
