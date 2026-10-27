# Support Ticket Filtering Specification

Version: v1
Status: current
Updated: 2026-10-27

## Scope

`filterTickets(tickets, filters)` filters a read-only list of support tickets.

## Required behavior

1. `filters.status` must perform an exact match when supplied.
2. `filters.minPriority` must be inclusive when supplied.
3. The function must return a new array and must not mutate the input tickets.
4. Invalid non-array input must throw `TypeError`.

## Compatibility

Filtering by status and minimum priority are existing public behaviors and must remain stable.
