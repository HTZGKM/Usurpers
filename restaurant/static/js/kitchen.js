function mountKitchenWorkspace(workspace) {
  const find = (selector) => workspace.querySelector(selector);
  const tickets = find("[data-kitchen-tickets]");
  const handoff = find("[data-kitchen-handoff]");
  const feedback = find("[data-kitchen-feedback]");
  const syncNotice = find("[data-kitchen-sync]");
  const stages = {
    waiting: ["Waiting", "Start preparation", "start"],
    cooking: ["Cooking", "Mark ready", "complete"],
    ready: ["Ready to serve", "", ""],
  };
  let view = "queue";
  let revision = 0;
  let pending = false;
  let polling = false;
  let refreshError = false;

  function queueAge(lines) {
    const enqueued = lines.map(line => {
      const stamp = line.created_at?.replace(" ", "T");
      return Date.parse(stamp && (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(stamp) ? stamp : stamp + "Z"));
    }).filter(Number.isFinite);
    if (!enqueued.length) return "";
    const minutes = Math.max(0, Math.floor((Date.now() - Math.min(...enqueued)) / 60000));
    return minutes ? "Queued " + minutes + " min ago" : "Just queued";
  }

  function renderQueue(rows, menuRows) {
    const names = new Map(menuRows.map(dish => [dish.dish_id, dish.dish_name]));
    const orders = new Map();
    for (const row of rows) {
      if (!orders.has(row.order_id)) orders.set(row.order_id, []);
      orders.get(row.order_id).push(row);
    }
    const activeTickets = [];
    const handoffTickets = [];
    for (const [order, lines] of orders) {
      const items = lines.map(line => {
        const [status, label, action] = stages[line.status];
        return '<li class="kitchen-item" data-stage="' + line.status + '"><div class="kitchen-item-copy"><strong>' +
          line.quantity + ' × ' + esc(names.get(line.dish_id) ?? "Dish #" + line.dish_id) +
          '</strong><span class="kitchen-item-stage">' + esc(status) + '</span>' +
          (line.note ? '<p class="kitchen-note"><b>Note</b> ' + esc(line.note) + '</p>' : '') + '</div>' +
          (action ? '<button type="button" class="kitchen-action" data-kitchen-item="' + line.order_item_id +
            '" data-kitchen-step="' + action + '">' + label + '</button>' : '') + '</li>';
      }).join("");
      const table = tableLabel(lines[0].table_id);
      const markup = '<article class="kitchen-ticket" data-kitchen-ticket="' + order + '" data-stage="' + lines[0].status +
        '"><div class="kitchen-ticket-heading"><div>' +
        '<h3 tabindex="-1">' + (table ? 'Table ' + esc(table) : 'Order #' + order) + '</h3><p>' +
        (table ? 'Order #' + order + ' · ' : '') + esc(queueAge(lines)) + '</p></div>' +
        '</div><ul class="kitchen-item-list">' + items + '</ul></article>';
      const destination = lines.every(line => line.status === "ready") ? handoffTickets : activeTickets;
      destination.push(markup);
    }

    const markup = activeTickets.join("") || '<p class="kitchen-empty">No dishes to prepare.</p>';
    const handoffMarkup = handoffTickets.join("");
    const focused = document.activeElement;
    const itemId = tickets.contains(focused) && focused.dataset.kitchenItem;
    const orderId = focused.closest("[data-kitchen-ticket]")?.dataset.kitchenTicket;
    const handoffHadFocus = handoff.contains(focused);
    const activeHadFocus = tickets.contains(focused);
    const activeChanged = tickets.innerHTML !== markup;
    const handoffChanged = handoff.innerHTML !== handoffMarkup;
    if (activeChanged) tickets.innerHTML = markup;
    if (handoffChanged) handoff.innerHTML = handoffMarkup;
    handoff.closest("section").hidden = !handoffTickets.length;
    if ((activeHadFocus && activeChanged) || (handoffHadFocus && handoffChanged)) {
      const target = itemId && find('[data-kitchen-item="' + itemId + '"]');
      (target || find('[data-kitchen-ticket="' + orderId + '"] h3') || find("#kitchen-queue-title")).focus({ preventScroll: true });
    }
    const count = activeTickets.length + (activeTickets.length === 1 ? " active order" : " active orders");
    const total = find("[data-kitchen-count]");
    if (total.textContent !== count) total.textContent = count;
    for (const stage of Object.keys(stages)) {
      const quantity = rows.filter(row => row.status === stage).reduce((sum, row) => sum + row.quantity, 0);
      const stageCount = find('[data-kitchen-stage="' + stage + '"]');
      if (stageCount.textContent !== String(quantity)) stageCount.textContent = quantity;
    }
  }

  function renderMenu(rows) {
    const listed = rows.filter(dish => !dish.is_archived);
    const categories = { burgers: "burger", pizzas: "pizza", sides: "sides", drinks: "drinks" };
    for (const group of workspace.querySelectorAll("[data-kitchen-category]")) {
      group.innerHTML = listed.filter(dish => (categories[dish.category] ?? "other") === group.dataset.kitchenCategory)
        .map(dish => {
          const next = !dish.is_available;
          const label = next ? "Mark available" : "Mark unavailable";
          return '<li class="kitchen-item"><div class="kitchen-item-copy"><strong>' + esc(dish.dish_name) +
            '</strong><p>' + (next ? "Unavailable" : "Available") +
            '</p></div><button type="button" class="kitchen-action" data-kitchen-dish="' + dish.dish_id +
            '" data-kitchen-next="' + next + '" aria-label="' + esc(label + ": " + dish.dish_name) + '">' +
            label + '</button></li>';
        }).join("") || '<li class="kitchen-item">No listed dishes.</li>';
      if (group.dataset.kitchenCategory === "other") group.closest("section").hidden =
        !listed.some(dish => !categories[dish.category]);
    }
    find("[data-availability-count]").textContent = listed.filter(dish => !dish.is_available).length + " unavailable";
  }

  async function refresh() {
    const current = ++revision;
    try {
      const { items: menuRows } = await restaurantRequest("/kitchen/menu");
      if (current !== revision) return;
      const rows = view === "queue" ? (await Promise.all(Object.keys(stages).map(status =>
        restaurantRequest(restaurantQuery("/kitchen/queue", { status }))
      ))).flatMap(result => result.items) : [];
      if (current !== revision) return;
      if (view === "queue") renderQueue(rows, menuRows);
      else renderMenu(menuRows);
      if (refreshError) feedback.textContent = "";
      refreshError = false;
      syncNotice.textContent = view === "queue" ? "Auto-updates on" : "";
      delete syncNotice.dataset.error;
      return true;
    } catch (error) {
      if (current === revision) {
        feedback.textContent = error.message;
        refreshError = true;
        if (view === "queue") {
          syncNotice.textContent = "Updates paused · Refresh";
          syncNotice.dataset.error = "true";
        }
      }
    }
  }

  workspace.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || pending) return;
    if (button.matches("[data-kitchen-refresh]")) {
      feedback.textContent = "";
      await refresh();
      return;
    }
    const { kitchenItem, kitchenStep, kitchenDish, kitchenNext } = button.dataset;
    if (!kitchenItem && !kitchenDish) return;
    pending = true;
    ++revision;
    const orderId = button.closest("[data-kitchen-ticket]")?.dataset.kitchenTicket;
    const requestedView = view;
    button.setAttribute("aria-disabled", "true");
    refreshError = false;
    feedback.textContent = "";
    try {
      if (kitchenItem) await restaurantRequest("/kitchen/items/" + kitchenItem + "/" + kitchenStep, {});
      else await restaurantRequest("/kitchen/menu/" + kitchenDish + "/availability", { is_available: kitchenNext });
      const refreshed = await refresh();
      if (!refreshed || requestedView !== view) return;
      if (kitchenStep === "complete") feedback.textContent = "Dish ready. Front desk can now mark it served.";
      const replacement = kitchenItem
        ? find('[data-kitchen-item="' + kitchenItem + '"]')
        : find('[data-kitchen-dish="' + kitchenDish + '"]');
      (replacement ?? find('[data-kitchen-ticket="' + orderId + '"] h3') ?? find("[data-kitchen-refresh]")).focus();
    } catch (error) {
      feedback.textContent = error.message;
      if (error.status === 409) await refresh();
    } finally {
      button.removeAttribute("aria-disabled");
      pending = false;
    }
  });

  async function poll() {
    if (view !== "queue" || pending || polling || document.hidden) return;
    polling = true;
    try {
      await refresh();
    } finally {
      polling = false;
    }
  }
  setInterval(poll, 5000);
  document.addEventListener("visibilitychange", poll);
  return (section, focus) => {
    view = section;
    const queue = find("#kitchen-queue");
    const availability = find("#kitchen-availability");
    queue.hidden = view !== "queue";
    availability.hidden = view !== "availability";
    if (focus) (view === "queue" ? queue : availability).querySelector("h2").focus();
    feedback.textContent = "";
    refresh();
  };
}
