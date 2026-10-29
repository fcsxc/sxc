---
id: SPEC-LOG-006
title: 退款审计日志字段（现行）
status: active
applies_to: orderflow.audit
supersedes: SPEC-LOG-004
tags: 日志,审计,可观测性
---

## 规则

1. 每笔退款写入一条结构化审计日志，字段为 `trace_id`、`operator`、`amount_cents`、`decided_at`、`reason`。
2. 日志中的 `amount_cents` 必须与退款单返回的 `refund_cents` 一致。

## 说明

`orderflow.audit` 模块目前尚未实现，本条与本次退款额度计算任务无直接关系。
