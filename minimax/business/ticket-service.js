/**
 * Filter support tickets without mutating the input array.
 *
 * Existing filters:
 * - status: exact match
 * - minPriority: inclusive lower bound
 *
 * Additional filter:
 * - text: case-insensitive substring match against title or description
 */
export function filterTickets(tickets, filters = {}) {
  if (!Array.isArray(tickets)) {
    throw new TypeError("tickets must be an array");
  }

  const text =
    typeof filters.text === "string" ? filters.text.trim().toLowerCase() : "";

  return tickets.filter((ticket) => {
    if (filters.status !== undefined && ticket.status !== filters.status) {
      return false;
    }

    if (filters.minPriority !== undefined && ticket.priority < filters.minPriority) {
      return false;
    }

    if (text !== "") {
      const title = typeof ticket.title === "string" ? ticket.title.toLowerCase() : "";
      const description =
        typeof ticket.description === "string" ? ticket.description.toLowerCase() : "";

      if (!title.includes(text) && !description.includes(text)) {
        return false;
      }
    }

    return true;
  });
}
