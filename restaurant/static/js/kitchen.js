function mountKitchenWorkspace(workspace) {
  const find = (selector) => workspace.querySelector(selector);
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
    const groups = Object.fromEntries(Object.keys(stages).map(stage => [stage, new Map()]));
    for (const row of rows) {
      const orders = groups[row.order_stage ?? row.status];
      if (!orders.has(row.order_id)) orders.set(row.order_id, []);
      orders.get(row.order_id).push(row);
    }
    const focused = document.activeElement;
    const focusedTicket = focused?.closest("[data-kitchen-ticket]");
    const itemId = focused?.dataset.kitchenItem;
    let restoreFocus = false;
    for (const [stage, orders] of Object.entries(groups)) {
      const [status, label, action] = stages[stage];
      const tickets = [...orders].map(([order, lines]) => {
        const items = lines.map(line => '<li class="kitchen-item" data-stage="' + stage + '" data-kitchen-line="' +
          line.order_item_id + '"><div class="kitchen-item-copy"><strong>' +
          line.quantity + ' × ' + esc(line.dish_name ?? names.get(line.dish_id) ?? "Dish #" + line.dish_id) +
          '</strong><span class="kitchen-item-stage">' + esc(line.supply_issue ? 'Needs guest decision: ' + line.supply_issue : line.item_status === 'ready' ? 'Dish ready' : line.item_status === 'cooking' ? 'Cooking' : 'Not started') + '</span>' +
          (line.note ? '<p class="kitchen-note"><b>Note</b> ' + esc(line.note) + '</p>' : '') + '</div>' +
          (line.item_status === "cooking" ? '<button type="button" class="kitchen-action" data-kitchen-item="' + line.order_item_id +
            '" data-kitchen-version="' + line.order_version + '" data-kitchen-step="complete">Mark dish ready</button>' : line.item_status === 'waiting' && !line.supply_issue ? '<button type="button" class="kitchen-action" data-kitchen-item="' + line.order_item_id + '" data-kitchen-version="' + line.order_version + '" data-kitchen-step="unavailable">Cannot supply</button>' : '') + '</li>').join("");
        const table = tableLabel(lines[0].table_id);
        const orderLabel = (lines[0].order_type === "preorder" ? "Preorder #" : "Order #") + order;
        const metadata = [table && orderLabel, queueAge(lines)].filter(Boolean).join(" · ");
        return '<article class="kitchen-ticket" data-kitchen-ticket="' + order + '" data-stage="' + stage +
          '"><div class="kitchen-ticket-heading"><div><h3 tabindex="-1">' + esc(table ? 'Table ' + table : orderLabel) +
          '</h3><p>' + esc(metadata) + '</p></div>' + (lines.some(line => line.item_status === 'waiting' && !line.supply_issue) ? '<button type="button" class="kitchen-action" data-start-order="' + order + '" data-kitchen-version="' + lines[0].order_version + '">Start order</button>' : '') + '</div><ul class="kitchen-item-list">' + items + '</ul></article>';
      }).join("");
      const column = find('[data-kitchen-lane="' + stage + '"]');
      const markup = tickets || '<p class="kitchen-empty">' + ({ waiting: "Nothing to start.",
        cooking: "Nothing cooking.", ready: "Nothing ready to serve." })[stage] + '</p>';
      if (column.innerHTML !== markup) {
        restoreFocus ||= column.contains(focused);
        column.innerHTML = markup;
      }
      const quantity = orders.size;
      const stageCount = find('[data-kitchen-stage="' + stage + '"]');
      if (stageCount.textContent !== String(quantity)) stageCount.textContent = quantity;
    }
    if (restoreFocus) {
      const heading = focusedTicket && find('[data-kitchen-ticket="' + focusedTicket.dataset.kitchenTicket +
        '"][data-stage="' + focusedTicket.dataset.stage + '"] h3');
      (itemFocus(itemId) ?? heading ?? find("#kitchen-queue-title")).focus({ preventScroll: true });
    }
    const size = new Set(rows.map(row => row.order_id)).size;
    const count = size + (size === 1 ? " active order" : " active orders");
    const total = find("[data-kitchen-count]");
    if (total.textContent !== count) total.textContent = count;
  }

  function itemFocus(itemId) {
    if (!itemId) return null;
    return find('[data-kitchen-item="' + itemId + '"]') ??
      find('[data-kitchen-line="' + itemId + '"]')?.closest('[data-kitchen-ticket]')?.querySelector('h3');
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
      if (view === "queue") await restaurantRefreshOperations();
      const [menu, queue, settings] = await Promise.all([
        restaurantRequest("/kitchen/menu"),
        view === "queue" ? restaurantRequest("/kitchen/queue?status=active") : null,
        restaurantRequest("/kitchen/settings"),
      ]);
      if (current !== revision) return;
      if (view === "queue") renderQueue(queue.items, menu.items);
      else renderMenu(menu.items);
      const capacity = find('[data-kitchen-capacity]');
      if (!capacity.contains(document.activeElement)) {
        capacity.elements.max_active_orders.value = settings.settings.max_active_orders;
        capacity.elements.expected_version.value = settings.settings.version;
      }
      find('[data-kitchen-capacity-count]').textContent = settings.settings.active_orders + ' orders cooking / ' + settings.settings.max_active_orders + ' limit';
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
    const { kitchenItem, kitchenStep, kitchenVersion, kitchenDish, kitchenNext, startOrder } = button.dataset;
    if (!kitchenItem && !kitchenDish && !startOrder) return;
    pending = true;
    ++revision;
    const orderId = button.closest("[data-kitchen-ticket]")?.dataset.kitchenTicket;
    const requestedView = view;
    button.setAttribute("aria-disabled", "true");
    refreshError = false;
    feedback.textContent = "";
    try {
      if (startOrder) await restaurantRequest('/kitchen/orders/' + startOrder + '/start', { expected_version: kitchenVersion });
      else if (kitchenStep === 'unavailable') {
        const reason = window.prompt('Why can this unstarted dish not be supplied?');
        if (!reason?.trim()) return;
        await restaurantRequest('/kitchen/items/' + kitchenItem + '/unavailable', { expected_version: kitchenVersion, reason });
      }
      else if (kitchenItem) await restaurantRequest("/kitchen/items/" + kitchenItem + "/" + kitchenStep,
        kitchenStep === "start" ? { expected_version: kitchenVersion } : {});
      else await restaurantRequest("/kitchen/menu/" + kitchenDish + "/availability", { is_available: kitchenNext });
      const refreshed = await refresh();
      if (!refreshed || requestedView !== view) return;
      if (kitchenStep === "complete") feedback.textContent = "Dish ready. The order reaches front desk when every remaining dish is ready.";
      const replacement = kitchenItem
        ? itemFocus(kitchenItem)
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

  find('[data-kitchen-capacity]').addEventListener('submit', async event => {
    event.preventDefault();
    if (pending) return;
    pending = true;
    try {
      await restaurantRequest('/kitchen/settings', Object.fromEntries(new FormData(event.target)));
      await refresh();
      feedback.textContent = 'Capacity saved. Existing work continues when the limit is lowered.';
    } catch (error) {
      feedback.textContent = error.message;
      const latest = await restaurantRequest('/kitchen/settings').catch(() => null);
      if (latest) {
        event.target.elements.max_active_orders.value = latest.settings.max_active_orders;
        event.target.elements.expected_version.value = latest.settings.version;
      }
    } finally { pending = false; }
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
