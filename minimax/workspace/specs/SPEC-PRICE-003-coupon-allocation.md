---
id: SPEC-PRICE-003
title: 订单实付金额与优惠券分摊
status: active
applies_to: orderflow.pricing
supersedes: ""
tags: 金额,优惠券,分摊,精度
---

## 规则

1. 所有金额一律使用「分」为单位的整数，不使用浮点数。
2. 商品小计 = 各行 `单价 × 数量` 之和。
3. 订单实付金额 = 商品小计 − 优惠券抵扣 + 运费。
4. 优惠券抵扣按退款涉及商品的金额占商品小计的比例分摊，分摊结果四舍五入到分，且不超过该行金额。
5. 分摊使用整数运算实现：`(numerator + denominator // 2) // denominator`。

## 验收

- `SPEC-PRICE-003` 相关回归用例在本次改动前后均须通过。
