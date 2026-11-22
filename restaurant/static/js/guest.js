const app = document.querySelector("#app"),
  nav = document.querySelector("#nav"),
  reduce = matchMedia("(prefers-reduced-motion: reduce)");
const dishSheet = document.querySelector(".dish-modal");
const {
  dishes,
  tables,
  slots,
  categories: cats,
  account,
  staffLinks,
} = JSON.parse(document.querySelector("#guest-data").textContent);
const isStaff = staffLinks.length > 0;
const customer = account?.role === "customer" ? account : null;
const loginPrompt = document.querySelector("#customer-login-prompt");
const menu = new Map(dishes.map((d) => [d.key, d]));
const imageBase = document.body.dataset.images;
function asset(dish, detail = false) {
  const folder = detail && dish.category === "pizza" ? "detail" : "catalog";
  return imageBase + folder + "/" + dish.key + ".webp";
}
function mount(name) {
  app.replaceChildren(
    document.getElementById("view-" + name).content.cloneNode(true),
  );
}
const today = () => {
  const d = new Date();
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
};
const blank = () => ({
  draft: {
    date: today(),
    guests: 2,
    time: "18:00",
    table: "",
    name: customer?.name || "Alex",
    phone: customer?.username || "139 0000 0001",
  },
  booking: null,
  checked: false,
  bag: [],
  bill: null,
  bookingHistory: [],
  orderHistory: [],
});
let state = blank(),
  edit = false;
const key = customer ? "double-portion-room-preview-v1." + customer.username : null;
try {
  const saved = key && JSON.parse(sessionStorage.getItem(key));
  if (saved?.draft) {
    const { bag, bill, paid, ...rest } = saved;
    state = {
      ...state,
      ...rest,
      bag: restoreMealBag(bag, menu),
      bill: restoreMealOrder(bill, menu, saved.booking?.table, paid),
    };
  }
} catch {}
function persist() {
  if (!key) return;
  try {
    sessionStorage.setItem(key, JSON.stringify(state));
  } catch {}
}
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const btn = (label, action, cls = "secondary", attrs = "") =>
  '<button type="button" class="' +
  cls +
  '" data-action="' +
  esc(action) +
  '" ' +
  attrs +
  ">" +
  esc(label) +
  "</button>";

const pair = (a, b) =>
  '<div class="pair"><span>' +
  esc(a) +
  "</span><strong>" +
  esc(b) +
  "</strong></div>";

const names = [
  "Home",
  "Book a table",
  "Menu",
  "Delivery",
  "Your table",
  "My account",
  "Journal",
];
const aliases = {
  home: "Home",
  menu: "Menu",
  delivery: "Delivery",
  booking: "Book a table",
  journal: "Journal",
  "Journal article": "Journal",
  account: "My account",
  workspace: "My account",
  "Sign in": "Book a table",
  "Choose a time": "Book a table",
  "Review reservation": "Book a table",
  "Reservation confirmed": "Book a table",
  "Reservation details": "Book a table",
  "Checked-in visit": "Your table",
  "Your bag": "Your table",
  "Review order": "Your table",
  "Order status": "Your table",
  "Confirm payment": "Your table",
  "Payment receipt": "Your table",
  "Bag empty": "Your table",
  "Awaiting check-in": "Your table",
  "Dish details": "Menu/pizza",
};
function route() {
  let raw;
  try {
    raw = decodeURIComponent(location.hash.slice(1));
  } catch {
    return "Home";
  }
  if (Object.hasOwn(aliases, raw)) raw = aliases[raw];
  if (raw.startsWith("workspace/")) return "My account";
  if (raw === "Journal/archive") return raw;
  if (raw.startsWith("Journal/")) return "Journal";
  if (raw.startsWith("Menu/category/") && Object.hasOwn(cats, raw.slice(14))) return raw;
  if (raw.startsWith("Menu/") && menu.has(raw.slice(5))) return raw;
  return names.includes(raw) ? raw : "Home";
}
function go(name) {
  if (nav.open) nav.close();
  if (route() !== name) location.hash = encodeURIComponent(name);
  else show(false);
}

let renderStaffSection;
const adminTableSections = ["tables/timeline", "tables/calendar"];

function showWorkspace(focus) {
  const defaultSection = staffLinks[0][1];
  const requestedSection = location.hash.startsWith("#workspace/") ? location.hash.slice(11) : "";
  const knownSection = staffLinks.some(([, key]) => key === requestedSection) ||
    (account.role === "admin" && adminTableSections.includes(requestedSection));
  const section = knownSection ? requestedSection : defaultSection;
  const hash = section === defaultSection ? "#workspace" : "#workspace/" + section;
  if (location.hash !== hash) history.replaceState(null, "", hash);
  if (!renderStaffSection) {
    const date = today();
    const demo = account.role === "admin" ? null : loadStaffDemo(dishes, date, slots);
    app.className = account.role + "-page";
    mount("workspace");
    if (account.role === "kitchen") {
      renderStaffSection = mountKitchenWorkspace(app.querySelector("[data-kitchen]"), account.username, demo);
    } else if (account.role === "frontdesk") {
      renderStaffSection = mountFrontdeskWorkspace(app.querySelector("[data-frontdesk]"), account.username, tables, slots, date, demo, goWorkspace);
    } else {
      renderStaffSection = mountAdminWorkspace(app.querySelector("[data-admin]"), tables, dishes, goWorkspace);
    }
    document.title = { frontdesk: "Front desk", kitchen: "Kitchen", admin: "Administrator" }[account.role] + " · Double Portion";
  }
  for (const link of document.querySelectorAll(".staff-nav-link")) {
    if (link.dataset.action === "workspace:" + section.split("/")[0]) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  renderStaffSection(section, focus);
}

function goWorkspace(section) {
  if (nav.open) nav.close();
  const hash = section === staffLinks[0][1] ? "#workspace" : "#workspace/" + section;
  if (account.role === "admin") {
    if (location.hash !== hash) history.pushState(null, "", hash);
    showWorkspace(true);
    return;
  }
  if (location.hash === hash) showWorkspace(true);
  else location.hash = hash;
}

function promptCustomerSignIn() {
  if (!loginPrompt) return;
  const view = route();
  loginPrompt.querySelector("[data-customer-login-copy]").textContent = view === "Book a table"
    ? "Sign in to check table availability and make a reservation."
    : view === "Your table" ? "Sign in to view your reservations, orders and bag."
      : "Sign in to add dishes to your bag.";
  loginPrompt.showModal();
}

function openCustomerLogin() {
  const returnTo = location.hash;
  loginPrompt.close();
  history.pushState({ returnTo }, "", "#My%20account");
  show(true);
}
function animate(el, ms) {
  if (!reduce.matches)
    el?.animate(
      [
        { opacity: 0.15, transform: "translateY(4px)" },
        { opacity: 1, transform: "none" },
      ],
      { duration: ms, easing: "ease-out" },
    );
}

function available(t, d) {
  const seed = Number(d.date.replaceAll("-", "")) + slots.indexOf(d.time);
  return t[1] >= d.guests && t[0] !== tables[seed % tables.length]?.[0];
}

function prettyDate(v) {
  return new Date(v + "T12:00:00").toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}
function bookingSummary(d) {
  return (
    prettyDate(d.date) +
    " · " +
    d.time +
    " · " +
    d.guests +
    (Number(d.guests) === 1 ? " guest" : " guests") +
    (d.table ? " · Table " + d.table : "")
  );
}
function bookingView() {
  mount("booking");
  if (!customer) return;
  const locked = !!state.booking && !edit;
  const d = locked ? state.booking : state.draft;
  const form = app.querySelector("#reservation");
  const heading = app.querySelector(".panel h2");
  if (locked) {
    heading.textContent = "Your reservation";
    const confirmation = document.createElement("div");
    let body;
    body =
      '<p class="notice"><span class="tick">✓</span>' +
      (state.checked
        ? "Checked in at table " + esc(d.table)
        : "Your table is reserved.") +
      "</p>" +
      pair("Guest", d.name) +
      pair("Reservation", bookingSummary(d)) +
      btn(
        state.checked ? "Explore the menu" : "Preview host check-in",
        state.checked ? "Menu" : "checkin",
        "primary",
      ) +
      (!state.checked
        ? btn("Edit reservation", "edit") +
          btn("Cancel reservation", "ask-cancel")
        : "") +
      '<div id="inline-confirm"></div>';
    confirmation.innerHTML = body;
    form.replaceWith(confirmation);
    app.querySelectorAll(".seat").forEach((button) => {
      button.disabled = true;
      button.setAttribute(
        "aria-pressed",
        button.dataset.action.slice(5) === d.table,
      );
    });
    return;
  }
  form.querySelector("#date").min = today();
  for (const field of ["date", "guests", "name", "phone"])
    form.querySelector("#" + field).value = d[field];
  if (edit) {
    heading.textContent = "Edit reservation";
    form.querySelector("[type=submit]").textContent = "Save reservation";
    form.insertAdjacentHTML(
      "afterend",
      btn("Keep original reservation", "discard"),
    );
  }
  syncDraft();
}
function syncDraft() {
  const d = state.draft;
  if (d.table && !tables.some((t) => t[0] === d.table && available(t, d)))
    d.table = "";
  document.querySelectorAll(".seat").forEach((b) => {
    const t = tables.find((t) => t[0] === b.dataset.action.slice(5));
    b.disabled = !available(t, d);
    b.setAttribute("aria-pressed", t[0] === d.table);
  });
  document
    .querySelectorAll('[data-action^="time:"]')
    .forEach((b) =>
      b.setAttribute("aria-pressed", b.dataset.action.slice(5) === d.time),
    );
  document.querySelector("#summary").textContent = d.table
    ? bookingSummary(d)
    : "Choose an available table on the floor plan.";
  document.querySelector(".statusline").textContent = "";
  persist();
}
function bagButton() {
  const value = mealTotal(state.bag);
  return value
    ? btn("View bag · ¥" + value, "Your table", "primary bag-bar")
    : "";
}
function menuView() {
  mount("menu");
  app.querySelector("#bag-entry").innerHTML = bagButton();
}
function scrollToMenuCategory(category, behavior = "instant") {
  document.getElementById("section-" + category)?.scrollIntoView({ behavior });
}
let detailKey = "",
  detailLineId = null,
  detailQty = 1;
function stepper(k, n) {
  return (
    '<div class="stepper">' +
    btn(
      "−",
      "minus:" + k,
      "",
      'aria-label="Decrease quantity" ' +
        (n <= 1 ? "disabled" : ""),
    ) +
    '<b aria-live="polite">' +
    n +
    "</b>" +
    btn(
      "+",
      "plus:" + k,
      "",
      'aria-label="Increase quantity" ' + (n >= 99 ? "disabled" : ""),
    ) +
    "</div>"
  );
}
function showDishChoices(dish, selected) {
  dishSheet.querySelector(".dish-configuration").innerHTML = optionsForDish(dish)
    .map(({ name, title, choices, multiple }) => (
      '<fieldset><legend>' + esc(title) + '</legend><div class="dish-choices">' +
      choices.map(([key, label, price]) => (
        '<label class="dish-choice"><input data-dish-option type="' +
        (multiple ? "checkbox" : "radio") + '" name="' + name + '" value="' + key + '"' +
        (selected.includes(key) ? " checked" : "") + '><span>' + esc(label) +
        (price ? ' <small>+¥' + price + '</small>' : '') + "</span></label>"
      )).join("") + "</div></fieldset>"
    )).join("");
}
function detailLine() {
  const selected = [...dishSheet.querySelectorAll("[data-dish-option]:checked")].map((option) => option.value);
  const note = dishSheet.querySelector(".dish-note textarea").value.trim();
  return makeMealLine(menu.get(detailKey), detailLineId, detailQty, selected, note);
}
function dishFeedback(message = "") {
  const feedback = dishSheet.querySelector(".dish-error");
  feedback.textContent = message;
  feedback.hidden = !message;
}
const rollingPrices = new WeakMap();
function updateRollingPrice(output, amount, animateChange = true) {
  const previous = rollingPrices.get(output);
  if (animateChange && previous?.amount === amount) return;

  const before = previous?.reels.length
    ? previous.reels.map(({ animation, digits, start, end }) => {
        const progress = animation.effect.getComputedTiming().progress ?? 0;
        return digits[Math.round(start + (end - start) * progress)];
      }).join("")
    : String(previous?.amount ?? amount);
  previous?.reels.forEach(({ animation }) => animation.cancel());

  const value = "¥" + amount;
  let accessibleValue = output.querySelector(".price-value");
  let display = output.querySelector(".price-reels");
  if (!display) {
    accessibleValue = document.createElement("span");
    accessibleValue.className = "price-value";
    display = document.createElement("span");
    display.className = "price-reels";
    display.setAttribute("aria-hidden", "true");
    output.replaceChildren(accessibleValue, display);
  }
  accessibleValue.textContent = value;
  const reels = [];
  const current = { amount, reels };
  rollingPrices.set(output, current);
  const after = String(amount);
  if (!previous || !animateChange || reduce.matches || !display.animate ||
      !/^\d+$/.test(after) || !/^[\d ]+$/.test(before)) {
    display.textContent = value;
    return;
  }

  const width = Math.max(before.length, after.length);
  const from = before.padStart(width);
  const to = after.padStart(width);
  const direction = amount > previous.amount ? 1 : -1;
  const stagger = Math.min(55, 110 / Math.max(1, width - 1));
  display.textContent = "¥";
  for (let index = 0; index < width; index++) {
    const reel = document.createElement("span");
    reel.className = "price-reel";
    const track = document.createElement("span");
    track.className = "price-track";
    const last = Number(to[index]);
    const digits = [from[index]];
    for (let step = 4; step > 0; step--) {
      digits.push(String((last - direction * step + 10) % 10));
    }
    digits.push(to[index]);
    if (direction < 0) digits.reverse();
    for (const digit of digits) {
      const cell = document.createElement("span");
      cell.className = "price-reel-digit";
      cell.textContent = digit;
      track.append(cell);
    }
    reel.append(track);
    display.append(reel);
    const start = direction > 0 ? 0 : digits.length - 1;
    const end = digits.length - 1 - start;
    const animation = track.animate(
      [start, end].map((position) => ({ transform: `translateY(${-100 * position / digits.length}%)` })),
      { duration: 340 + (width - 1 - index) * stagger, easing: "cubic-bezier(.16,.72,.35,1)", fill: "both" },
    );
    reels.push({ animation, digits, start, end });
  }
  Promise.allSettled(reels.map(({ animation }) => animation.finished)).then(() => {
    if (rollingPrices.get(output) !== current) return;
    display.textContent = value;
    reels.length = 0;
  });
}

function updateDetail(animatePrice = true) {
  const line = detailLine();
  dishFeedback();
  dishSheet.querySelector("[data-dish-quantity]").innerHTML = stepper("detail", detailQty);
  updateRollingPrice(dishSheet.querySelector("[data-dish-total]"), mealTotal([line]), animatePrice);
}
function showDetail(k, lineId = null) {
  if (detailKey === k && detailLineId === lineId && dishSheet.open) return;
  const dish = menu.get(k);
  const editingLine = state.bag.find((line) => line.id === lineId);
  detailKey = k;
  detailLineId = lineId;
  detailQty = editingLine?.quantity ?? 1;
  const im = dishSheet.querySelector("img");
  im.onload = () =>
    im.style.setProperty(
      "--img-limit",
      im.naturalWidth / Math.max(1, devicePixelRatio) + "px",
    );
  im.src = asset(dish, true);
  im.alt = dish.name;
  dishSheet.querySelector(".context").textContent = editingLine ? "Edit bag item" : cats[dish.category];
  dishSheet.querySelector("#dish-name").textContent = dish.name;
  dishSheet.querySelector(".dish-description").textContent = dish.description;
  const action = dishSheet.querySelector(".primary");
  action.disabled = dish.sold;
  action.dataset.action = !customer ? "customer-sign-in" : state.bill ? "Your table" : "add";
  action.textContent = dish.sold
    ? "Sold out"
    : state.bill
      ? "View your order"
      : editingLine ? "Save changes" : "Add to bag";
  const previewPrice = dishSheet.querySelector(".dish-preview-price");
  previewPrice.hidden = Boolean(customer) || dish.sold;
  previewPrice.textContent = "¥" + dish.price;
  const canCustomize = Boolean(customer) && !dish.sold && !state.bill;
  dishSheet.querySelector(".dish-customization").hidden = !canCustomize;
  dishSheet.querySelector(".dish-options").hidden = !canCustomize;
  dishFeedback();
  if (canCustomize) {
    const defaults = makeMealLine(dish, lineId, detailQty).options;
    showDishChoices(dish, editingLine?.options ?? defaults);
    dishSheet.querySelector(".dish-note textarea").value = editingLine?.note ?? "";
    updateDetail(false);
  }
  if (!dishSheet.open) dishSheet.showModal();
  dishSheet.scrollTop = 0;
  animate(dishSheet, 180);
}
function leaveDetail() {
  if (detailLineId !== null) {
    dishSheet.close();
    detailKey = "";
    detailLineId = null;
  } else if (history.state?.dishFromMenu) history.back();
  else {
    history.replaceState(null, "", "#Menu");
    show(false);
  }
}
function saveDetailToBag() {
  const line = detailLine();
  const match = state.bag.find((item) =>
    item.id !== detailLineId && item.key === line.key &&
    item.note === line.note && item.options.join("|") === line.options.join("|"),
  );
  if (match && match.quantity + line.quantity > 99) {
    dishFeedback("You can keep up to 99 of the same item and options in your bag.");
    return;
  }
  const editing = detailLineId !== null;
  if (match) {
    match.quantity += line.quantity;
    if (editing) state.bag = state.bag.filter((item) => item.id !== detailLineId);
  } else if (editing) {
    state.bag = state.bag.map((item) => item.id === detailLineId ? line : item);
  } else {
    line.id = state.bag.reduce((highest, item) => Math.max(highest, item.id), 0) + 1;
    state.bag.push(line);
  }
  persist();
  leaveDetail();
  if (editing) show(false);
}

function mealLineMarkup(line, editable = false) {
  const unavailable = editable && menu.get(line.key)?.sold;
  return '<article class="order-line" aria-label="' + esc(line.name) + '">' +
    '<div class="order-line-copy"><strong>' + esc(line.name) + '</strong><small>¥' + line.unitPrice + ' each</small>' +
    (line.labels.length ? '<small>' + esc(line.labels.join(" · ")) + '</small>' : '') +
    (line.note ? '<small>Kitchen note: ' + esc(line.note) + '</small>' : '') +
    (unavailable ? '<small class="order-unavailable">Sold out</small>' : '') +
    '</div><div class="order-line-amount">' +
    (editable ? '' : '<small>× ' + line.quantity + '</small>') +
    '<b>¥' + mealTotal([line]) + '</b></div>' +
    (editable ? '<div class="order-line-actions">' +
      (unavailable ? '<span>× ' + line.quantity + '</span>' : stepper(line.id, line.quantity) + btn("Edit item", "edit-line:" + line.id, "bag-line-button")) +
      btn("Remove", "remove-line:" + line.id, "bag-line-button") + '</div>' : '') +
    '</article>';
}
function renderVisitHistory() {
  const section = app.querySelector("[data-visit-history]");
  if (!section) return;
  const reservations = [...state.bookingHistory];
  if (state.booking) reservations.unshift({
    ...state.booking,
    status: state.bill?.paid ? "Completed" : state.checked ? "Checked in" : "Reserved",
  });
  const orders = [state.bill, ...state.orderHistory].filter(Boolean);
  const bookingRecords = reservations.map((booking, index) =>
    '<article class="history-record">' +
    '<div class="history-record-top"><strong>' + esc(bookingSummary(booking)) +
    '</strong><span class="history-status">' + esc(booking.status) + '</span></div>' +
    (state.booking && index === 0 ? btn("View reservation", "Book a table", "bag-line-button") : '') +
    '</article>',
  ).join("");
  const orderRecords = orders.map((order) => {
    const date = order.placedAt
      ? new Date(order.placedAt).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })
      : "Earlier demo order";
    const table = order.table ? "Table " + order.table + " · " : "";
    return '<details class="history-record"><summary><strong>' + esc(table) + '¥' + mealTotal(order.lines) +
      '</strong><span class="history-status">' + (order.paid ? "Paid · demo" : "Awaiting demo payment") +
      '</span><small>' + esc(date) + '</small></summary>' +
      order.lines.map((line) => mealLineMarkup(line)).join("") + '</details>';
  }).join("");
  section.innerHTML =
    '<p class="history-caption">Demo records are saved in this tab.</p>' +
    '<section class="history-group"><h3>My reservations</h3>' +
    (bookingRecords || '<p class="history-empty">No reservations yet.</p>') +
    '</section><section class="history-group"><h3>My orders</h3>' +
    (orderRecords || '<p class="history-empty">No orders yet.</p>') + '</section>';
}
function visitView() {
  if (!customer) {
    mount("table");
    return;
  }
  const previousTotal = app.querySelector("[data-bag-total]");
  const booked = state.booking;
  const order = state.bill;
  const lines = order?.lines ?? state.bag;
  const value = mealTotal(lines);
  const blocked = !order && lines.some((line) => menu.get(line.key)?.sold);
  let body = booked
    ? pair(
        "Table " + booked.table,
        state.checked ? "Checked in" : bookingSummary(booked),
      )
    : "";
  body += '<div id="lines">' + lines.map((line) => mealLineMarkup(line, !order)).join("") + "</div>";
  if (lines.length) {
    body += order ? pair(order.paid ? "Paid" : "Total", "¥" + value) :
      '<div class="pair"><span>Total</span><strong class="rolling-price" data-bag-total aria-live="polite" aria-atomic="true"></strong></div>';
  }
  if (order?.paid)
    body +=
      '<p class="notice" role="status"><span class="tick">✓</span>Demo payment received.</p>' +
      btn("Book another visit", "new-visit", "primary");
  else if (order)
    body +=
      "<p>Demo order submitted.</p>" +
      btn("Pay ¥" + value + " · demo", "pay", "primary");
  else if (!state.checked) {
    body +=
      "<p>" +
      (booked
        ? "Check in with your host before placing a dine-in order."
        : "Book a table and check in with your host to place a dine-in order.") +
      "</p>" +
      btn(
        booked ? "Preview host check-in" : "Book a table",
        booked ? "checkin" : "Book a table",
        "primary",
      ) +
      btn("Explore the menu", "Menu");
  } else {
    body += lines.length
      ? (blocked ? '<p class="order-unavailable">Remove sold-out items before placing an order.</p>' : '') +
        btn("Place order", "order", "primary", blocked ? "disabled" : "") + btn("Add another dish", "Menu")
      : "<p>Your bag is empty.</p>" +
        btn("Explore the menu", "Menu", "primary");
  }
  mount("table");
  app.querySelector(".panel h2").textContent = order?.paid
    ? "Payment received"
    : order
      ? "Order received"
      : lines.length
        ? "Your bag"
        : "Your visit";
  app.querySelector("[data-details]").innerHTML = body;
  const total = app.querySelector("[data-bag-total]");
  if (total) {
    if (previousTotal) total.replaceWith(previousTotal);
    updateRollingPrice(previousTotal ?? total, value);
  }
  renderVisitHistory();
}

let previousPage = "",
  menuScroll = 0;
function show(transition = true) {
  if (isStaff) {
    showWorkspace(transition);
    return;
  }
  const raw = route();
  const page = raw.startsWith("Menu/") ? "Menu" : raw;
  const category = raw.startsWith("Menu/category/") ? raw.slice(14) : "";
  const dish = page === "Menu" && !category ? raw.slice(5) : "";
  const wasDishOpen = dishSheet.open;
  if (wasDishOpen && !dish) {
    dishSheet.close();
    detailKey = "";
    detailLineId = null;
  }
  if (page === "Menu" && previousPage === "Menu") {
    if (dish) showDetail(dish);
    else {
      document.querySelector("#bag-entry").innerHTML = bagButton();
      if (category && !wasDishOpen) scrollToMenuCategory(category);
    }
    return;
  }
  if (previousPage === "Menu") menuScroll = scrollY;
  const changed = previousPage !== page,
    focusAction = document.activeElement?.dataset.action;
  previousPage = page;
  app.className = {
    Home: "home",
    "Book a table": "booking",
    "Your table": "visit",
    Menu: "menu-page",
    "My account": "account-page",
    Delivery: "delivery-page",
    Journal: "journal-page",
    "Journal/archive": "journal-archive-page",
  }[page] ?? "";
  if (page === "Book a table") bookingView();
  else if (page === "Menu") menuView();
  else if (page === "Your table") visitView();
  else if (page === "My account") {
    mount("account");
    if (customer) renderVisitHistory();
    if (!account && history.state?.signedOut) {
      history.replaceState(null, "");
      setAccountMode("login", "You have signed out.");
    }
  } else {
    mount({ Home: "home", Delivery: "delivery", Journal: "journal", "Journal/archive": "journal-archive" }[page]);
  }
  const coverHeader = app.querySelector(".cover > header");
  if (coverHeader) installNavLens(coverHeader);
  const heading = app.querySelector(page === "Journal/archive" ? "h1" : "h2");
  const pageTitle = { "Journal/archive": "Journal archive", "Your table": "Your visit" }[page] ?? page;
  document.title = pageTitle + " · Double Portion";
  if (changed) {
    window.scrollTo(0, page === "Menu" ? menuScroll : 0);
    if (transition) {
      heading?.focus({ preventScroll: true });
      animate(app.querySelector(".delivery-grid,.panel,.cards"), 240);
    }
  } else if (focusAction) {
    [...app.querySelectorAll("[data-action]")]
      .find((b) => b.dataset.action === focusAction && !b.disabled)
      ?.focus({ preventScroll: true });
  }
  if (dish) showDetail(dish);
  else if (category) scrollToMenuCategory(category);
}

function setAccountMode(mode, message = "") {
  app.querySelector(".panel h2").textContent = mode === "login" ? "Sign in" : "Create an account";
  for (const button of app.querySelectorAll("[data-account-mode]")) {
    button.setAttribute("aria-pressed", button.dataset.accountMode === mode);
  }
  for (const form of app.querySelectorAll("[data-account-form]")) {
    form.hidden = form.dataset.accountForm !== mode;
  }
  const notice = app.querySelector("[data-account-notice]");
  notice.textContent = message;
  notice.hidden = !message;
}

function showAccountFeedback(form, errors = {}, message = "") {
  let firstInvalid;
  for (const feedback of form.querySelectorAll("[data-field-error]")) {
    const name = feedback.dataset.fieldError;
    const field = form.elements.namedItem(name);
    const messages = errors[name] ?? [];
    feedback.textContent = messages.join(" ");
    feedback.hidden = !messages.length;
    if (messages.length) {
      field.setAttribute("aria-invalid", "true");
      firstInvalid ??= field;
    } else {
      field.removeAttribute("aria-invalid");
    }
  }
  const summary = form.querySelector("[data-form-feedback]");
  summary.textContent = message;
  summary.hidden = !message;
  if (firstInvalid) firstInvalid.focus();
  else if (message) summary.focus();
}

async function showAuthResponseError(form, response) {
  const document = new DOMParser().parseFromString(await response.text(), "text/html");
  if (!form.isConnected) return;
  const errors = {};
  for (const error of document.querySelectorAll("[data-form-error]")) {
    const field = error.dataset.formError;
    (errors[field] ??= []).push(error.textContent.trim());
  }
  const expired = errors.csrf_token || (form.dataset.accountForm === "logout" && response.status === 400);
  const message = expired
    ? "Your form has expired. Refresh the page and try again."
    : Object.keys(errors).length ? "" : "We couldn't complete your request. Please try again.";
  showAccountFeedback(form, errors, message);
}

let accountRequestPending = false;
async function submitAccountForm(form) {
  if (accountRequestPending) return;
  accountRequestPending = true;
  const mode = form.dataset.accountForm;
  const fields = new URLSearchParams(new FormData(form));
  const submit = form.querySelector('[type="submit"]');
  const originalLabel = submit.textContent;
  const modeButtons = app.querySelectorAll("[data-account-mode]");
  showAccountFeedback(form);
  const notice = app.querySelector("[data-account-notice]");
  if (notice) notice.hidden = true;
  form.setAttribute("aria-busy", "true");
  submit.disabled = true;
  submit.textContent = submit.dataset.pendingLabel;
  modeButtons.forEach((button) => { button.disabled = true; });

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: fields,
    });
    if (!response.ok || !response.redirected) {
      await showAuthResponseError(form, response);
      return;
    }
    if (mode !== "register") {
      // Refresh the server-rendered identity and start using its sessionStorage key.
      if (mode === "logout") {
        history.replaceState({ signedOut: true }, "", "#My%20account");
      }
      location.reload();
      return;
    }
    if (form.isConnected) {
      form.reset();
      setAccountMode("login", "Your account is ready. Sign in with your phone number.");
      const login = app.querySelector("#guest-login");
      login.reset();
      showAccountFeedback(login);
      login.elements.account.value = fields.get("phone_number").trim();
      login.elements.password.focus();
    }
  } catch {
    if (form.isConnected) showAccountFeedback(form, {}, "Could not connect. Check your connection and try again.");
  } finally {
    accountRequestPending = false;
    form.removeAttribute("aria-busy");
    submit.disabled = false;
    submit.textContent = originalLabel;
    modeButtons.forEach((button) => { button.disabled = false; });
  }
}

document.querySelector("#close").onclick = () => nav.close();
dishSheet?.addEventListener("cancel", (e) => {
  e.preventDefault();
  leaveDetail();
});
dishSheet?.addEventListener("click", (e) => {
  if (e.target === dishSheet) {
    const r = dishSheet.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      leaveDetail();
  }
});
document.addEventListener("input", (e) => {
  if (
    customer && e.target.closest("#reservation") &&
    ["name", "phone"].includes(e.target.id)
  ) {
    state.draft[e.target.id] = e.target.value;
    persist();
  }
});
document.addEventListener("change", (e) => {
  if (!customer) return;
  if (e.target.matches("[data-dish-option]")) {
    updateDetail();
    return;
  }
  if (e.target.id === "date" || e.target.id === "guests") {
    state.draft[e.target.id] =
      e.target.id === "guests" ? +e.target.value : e.target.value;
    syncDraft();
  }
});
document.addEventListener("submit", (e) => {
  if (e.target.matches("[data-account-form]")) {
    e.preventDefault();
    submitAccountForm(e.target);
    return;
  }
  if (e.target.id !== "reservation") return;
  e.preventDefault();
  if (!customer) return;
  const d = state.draft,
    err = e.target.querySelector(".statusline"),
    f = e.target;
  d.name = f.querySelector("#name").value.trim();
  d.phone = f.querySelector("#phone").value.trim();
  d.date = f.querySelector("#date").value;
  if (!d.name || !d.phone.match(/^[+\d ()-]{6,24}$/)) {
    err.textContent = "Enter a name and valid phone number.";
    return;
  }
  if (!d.table || !tables.some((t) => t[0] === d.table && available(t, d))) {
    err.textContent = "Select an available table on the floor plan.";
    document.querySelector(".seat:enabled")?.focus();
    return;
  }
  state.booking = { ...d };
  edit = false;
  persist();
  show(false);
  document.querySelector("h2")?.focus({ preventScroll: true });
  animate(document.querySelector(".notice"), 200);
});
document.addEventListener("click", (e) => {
  const modeButton = e.target.closest("[data-account-mode]");
  if (modeButton && !modeButton.disabled) {
    if (modeButton.getAttribute("aria-pressed") !== "true") {
      setAccountMode(modeButton.dataset.accountMode);
    }
    return;
  }
  const b = e.target.closest("button[data-action]");
  if (!b || b.disabled) return;
  const a = b.dataset.action;
  if (a === "navigation") {
    nav.showModal();
    animate(nav, 200);
    return;
  }
  if (isStaff) {
    if (a.startsWith("workspace:")) goWorkspace(a.slice(10));
    return;
  }
  if (names.includes(a)) {
    go(a);
    return;
  }
  if (a === "customer-sign-in") {
    promptCustomerSignIn();
    return;
  }
  if (a === "open-customer-login") {
    openCustomerLogin();
    return;
  }
  if (a.startsWith("section:")) {
    scrollToMenuCategory(a.slice(8), reduce.matches ? "instant" : "smooth");
    return;
  }
  if (a.startsWith("archive-post:")) {
    const post = document.getElementById(b.getAttribute("aria-controls"));
    post?.focus({ preventScroll: true });
    post?.scrollIntoView({ behavior: reduce.matches ? "instant" : "smooth" });
    return;
  }
  if (a.startsWith("dish:")) {
    history.pushState({ dishFromMenu: true }, "", "#Menu/" + a.slice(5));
    show(false);
    return;
  }
  if (a === "close-dish") {
    leaveDetail();
    return;
  }
  if (!customer) return;
  if (a.startsWith("seat:") || a.startsWith("time:")) {
    if (state.booking && !edit) return;
    if (a.startsWith("seat:")) state.draft.table = a.slice(5);
    else state.draft.time = a.slice(5);
    syncDraft();
    return;
  }
  if (a === "edit") {
    state.draft = { ...state.booking };
    edit = true;
    show(false);
    return;
  }
  if (a === "discard") {
    edit = false;
    state.draft = { ...state.booking };
    show(false);
    return;
  }
  if (a === "ask-cancel") {
    document.querySelector("#inline-confirm").innerHTML =
      "<p>Release this table?</p>" +
      btn("Keep reservation", "keep", "choice") +
      btn("Yes, cancel", "cancel", "choice");
    return;
  }
  if (a === "keep") {
    document.querySelector("#inline-confirm").replaceChildren();
    return;
  }
  if (a === "cancel") {
    if (!state.booking || state.checked) return;
    state.bookingHistory.unshift({ ...state.booking, status: "Cancelled" });
    state.booking = null;
    state.draft.table = "";
    edit = false;
    persist();
    show(false);
    return;
  }
  if (a === "checkin" && state.booking) {
    state.checked = true;
    edit = false;
    persist();
    go(state.bag.length ? "Your table" : "Menu");
    return;
  }
  if (a.startsWith("edit-line:") || a.startsWith("remove-line:")) {
    if (state.bill) return;
    const [command, id] = a.split(":");
    const line = state.bag.find((item) => item.id === Number(id));
    if (!line) return;
    if (command === "edit-line") {
      showDetail(line.key, line.id);
    } else {
      state.bag = state.bag.filter((item) => item.id !== line.id);
      persist();
      show(false);
      app.querySelector("#lines button:enabled")?.focus({ preventScroll: true });
      if (!state.bag.length) app.querySelector(".panel h2").focus({ preventScroll: true });
    }
    return;
  }
  if (a.startsWith("plus:") || a.startsWith("minus:")) {
    const [dir, k] = a.split(":"),
      delta = dir === "plus" ? 1 : -1;
    if (k === "detail") {
      detailQty = Math.min(99, Math.max(1, detailQty + delta));
      updateDetail();
      dishSheet
        .querySelector('[data-action="' + a + '"]:enabled')
        ?.focus({ preventScroll: true });
    } else if (!state.bill) {
      const line = state.bag.find((item) => item.id === Number(k));
      if (!line) return;
      line.quantity = Math.min(99, Math.max(1, line.quantity + delta));
      persist();
      show(false);
    }
    return;
  }
  if (a === "add" && detailKey && !state.bill && !menu.get(detailKey).sold) {
    saveDetailToBag();
    return;
  }
  if (a === "order" && state.checked && state.booking && !state.bill && state.bag.length) {
    if (state.bag.some((line) => menu.get(line.key)?.sold)) return;
    state.bill = {
      table: state.booking.table,
      placedAt: new Date().toISOString(),
      paid: false,
      lines: state.bag,
    };
    state.bag = [];
    persist();
    show(false);
    animate(document.querySelector("h2"), 200);
    return;
  }
  if (a === "pay" && state.bill && !state.bill.paid) {
    state.bill.paid = true;
    persist();
    show(false);
    animate(document.querySelector(".notice"), 220);
    return;
  }
  if (a === "new-visit" && state.bill?.paid) {
    const { booking, bill, bookingHistory, orderHistory } = state;
    state = { ...blank(), bookingHistory, orderHistory: [bill, ...orderHistory] };
    if (booking) state.bookingHistory.unshift({ ...booking, status: "Completed" });
    edit = false;
    persist();
    go("Book a table");
  }
});
window.addEventListener("hashchange", () => show(true));
if (customer && history.state?.returnTo?.startsWith("#")) {
  history.replaceState(null, "", history.state.returnTo);
}
show(false);
