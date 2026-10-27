# Support Ticket Filtering Specification

Version: v2
Status: current
Updated: 2026-10-27

## Scope

`filterTickets(tickets, filters)` filters a read-only list of support tickets.

## Required behavior

1. `filters.status` must perform an exact match when supplied.
2. `filters.minPriority` must be inclusive when supplied.
3. When `filters.text` is a non-empty string, matching must be case-insensitive and must test both `ticket.title` and `ticket.description`. Leading and trailing whitespace in the query must be ignored. An empty or whitespace-only query must not filter out tickets.
4. All supplied filters must be combined with logical AND.
5. The function must return a new array and must not mutate the input tickets.
6. Invalid non-array input must throw `TypeError`.

## Compatibility

Filtering by status and minimum priority are existing public behaviors and must remain stable. The text filter is additive and must not alter results when omitted or blank.
