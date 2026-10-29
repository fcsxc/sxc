---
id: SPEC-REFUND-001
title: 退款原因枚举与必填校验
status: active
applies_to: orderflow.refund,orderflow.service
supersedes: ""
tags: 退款,原因,校验,枚举
---

## 规则

1. 退款申请必须携带 `reason` 字段，取值必须属于退款原因枚举。
2. 退款原因枚举为：`damaged`（商品损坏）、`quality_issue`（质量问题）、`delivery_delay`（配送延迟）、`wrong_item`（错发商品）、`other`（其他）。
3. 原因不在枚举内时必须拒绝请求并抛出 `ValueError`，不得静默降级为 `other`。
4. 原因枚举由 `orderflow.models.REFUND_REASONS` 暴露，服务层通过 `RefundService.list_refundable_reasons()` 返回。

## 验收

- 传入 `not_a_reason` 时 `refundable_amount` 抛出 `ValueError`。
- 合法原因不抛出异常。
