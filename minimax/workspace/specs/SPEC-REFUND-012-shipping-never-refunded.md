---
id: SPEC-REFUND-012
title: 运费一律不予退款
status: superseded
applies_to: orderflow.refund
supersedes: ""
tags: 退款,运费
---

## 规则

1. 任何退款原因下，运费均不予退款。
2. 可退金额 = 退款商品金额 − 分摊的优惠券抵扣。

## 失效说明

本条目已被 `SPEC-REFUND-014` 取代：配送延迟场景下运费可以退款。
上下文模块在选择当前有效规格时**不得**把本条目作为约束提供给开发助手。
