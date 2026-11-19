const staffDemoKey = "double-portion-staff-preview-v1";

function readStaffPreview(key) {
  try {
    return JSON.parse(sessionStorage.getItem(key));
  } catch {
    return null;
  }
}

function loadStaffDemo(catalog, date, slots) {
  const accounts = [
    { id: 1, name: "Ava Chen", role: "customer", phone: "13900000101", active: true },
    { id: 2, name: "Elliot Park", role: "customer", phone: "13900000102", active: true },
    { id: 3, name: "Jamie Chen", role: "frontdesk", phone: "13900000120", email: "jamie@example.test", active: true },
    { id: 4, name: "Sam Lin", role: "kitchen", phone: "13900000121", email: "sam@example.test", active: true },
  ];
  const saved = readStaffPreview(staffDemoKey);
  if (saved) return { ...saved, accounts: saved.accounts ?? accounts };
  const dishes = catalog.map((dish) => ({ ...dish }));
  const menu = new Map(dishes.map((dish) => [dish.key, dish]));
  const orders = [
    [1042, "A2", [["pizza", 2, "Slice into eight."], ["fries", 1, ""]]],
    [1043, "B1", [["double", 1, "No pickles."], ["chicken", 2, ""]]],
    [1044, "C2", [["mushroom", 1, "Extra mushrooms."], ["bianca", 1, ""]]],
  ].map(([id, table, items], position) => ({
    id, table, date, time: ["17:32", "17:38", "17:44"][position], paidAt: null,
    items: items.map(([key, quantity, note], index) => ({
      id: index + 1, key, name: menu.get(key)?.name ?? key, price: menu.get(key)?.price ?? 0,
      quantity, note, status: "Queued",
    })),
  }));
  return {
    orders, dishes, accounts,
    reception: {
      bookings: [
        { id: 301, name: "Ava Chen", phone: "139 0000 0101", time: slots[0], guests: 2, table: "A1" },
        { id: 302, name: "Elliot Park", phone: "139 0000 0102", time: slots[0], guests: 2, table: "C1" },
        { id: 303, name: "Daniel Wu", phone: "139 0000 0103", time: slots[1], guests: 4, table: "B2" },
        { id: 304, name: "Mia Lin", phone: "139 0000 0104", time: slots[1], guests: 3, table: "" },
        { id: 305, name: "Noah Lu", phone: "139 0000 0105", time: slots[2], guests: 6, table: "C2" },
      ].map((booking) => ({ ...booking, date })),
      arrivals: { 302: "C1" }, walkIns: [],
    },
  };
}

function saveStaffDemo(demo) {
  try {
    sessionStorage.setItem(staffDemoKey, JSON.stringify(demo));
  } catch {}
}

function staffOrderTotal(order) {
  const cents = order.items.reduce((sum, item) => item.status === "Cancelled"
    ? sum : sum + Math.round(item.price * 100) * item.quantity, 0);
  return cents / 100;
}

function staffPrice(value) {
  return "¥" + value.toLocaleString("en", { maximumFractionDigits: 2 });
}

function staffOrderStatus(order) {
  const items = order.items.filter((item) => item.status !== "Cancelled");
  if (items.length === 0) return "Cancelled";
  if (items.every((item) => item.status === "Served")) return "Served";
  if (items.some((item) => item.status === "Queued")) return "In queue";
  return "Ready";
}

function staffActiveVisit({ bookings, arrivals, walkIns }, table, date) {
  const booking = bookings.find((entry) => entry.date === date && !entry.closedAt && arrivals[entry.id] === table);
  if (booking) return { status: "Occupied", booking };
  const walkIn = walkIns.find((entry) => entry.date === date && !entry.closedAt && entry.table === table);
  return walkIn ? { status: "Occupied", walkIn } : null;
}

function staffTableState(reception, table, day, slot, today) {
  const occupied = day === today && staffActiveVisit(reception, table, today);
  if (occupied) return occupied;
  const reserved = reception.bookings.find((booking) => booking.date === day && !booking.cancelled &&
    !reception.arrivals[booking.id] && booking.table === table && (!slot || booking.time === slot));
  return reserved ? { status: "Reserved", booking: reserved } : { status: "Available" };
}
