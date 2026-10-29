---
id: SPEC-REFUND-014
title: 退款额度计算规则
status: active
applies_to: orderflow.refund
supersedes: SPEC-REFUND-012
tags: 退款,额度,运费,规则
---

## 规则

1. 可退商品金额 = 退款商品小计 − 分摊到这些商品的优惠券抵扣。退款商品小计按 `单价 × 数量` 计算。
2. 优惠券抵扣按商品小计比例分摊，分摊结果四舍五入到分（见 `SPEC-PRICE-003`）。
3. 运费可退条件：仅当 `reason == "delivery_delay"`（配送延迟）时运费全额可退；其余原因运费不可退，`shipping_refund_cents` 为 0。
4. 可退金额 = 可退商品金额 + 可退运费，并受 `SPEC-REFUND-020` 的单次上限约束。
5. 当可退金额被上限截断时，`clamped` 必须为 `True`。
6. 退款商品必须属于该订单；未知 SKU 必须拒绝并抛出 `ValueError`。

## 失效的旧规则

`SPEC-REFUND-012`（运费一律不退）已被本条目取代，不得继续作为约束。

## 验收

- `damaged` 订单中运费不可退，`delivery_delay` 订单中运费可退。
- 超过上限时 `refundable_cents` 等于上限且 `clamped` 为 `True`。
