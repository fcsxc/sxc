/**
 * Filter support tickets without mutating the input array.
 *
 * Existing filters:
 * - status: exact match
 * - minPriority: inclusive lower bound
 */
export function filterTickets(tickets, filters = {}) {
  if (!Array.isArray(tickets)) {
    throw new TypeError("tickets must be an array");
  }
  return tickets.filter((ticket) => {
    if (filters.status !== undefined && ticket.status !== filters.status) {
      return false;
    }
    if (filters.minPriority !== undefined && ticket.priority < filters.minPriority) {
      return false;
    }
    return true;
  });
}
