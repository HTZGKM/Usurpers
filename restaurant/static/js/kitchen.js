function mountKitchenWorkspace(workspace) {
  const find = (selector) => workspace.querySelector(selector);
  const tickets = find("[data-kitchen-tickets]");
  const feedback = find("[data-kitchen-feedback]");
  const stages = {
    waiting: ["Waiting", "Start preparation", "start"],
    cooking: ["Cooking", "Mark ready", "complete"],
    ready: ["Ready for front desk", "", ""],
  };
  let view = "queue";
  let revision = 0;
  let pending = false;

  function renderQueue(rows, menuRows) {
    const names = new Map(menuRows.map(dish => [dish.dish_id, dish.dish_name]));
    const orders = new Map();
    for (const row of rows) {
      if (!orders.has(row.order_id)) orders.set(row.order_id, []);
      orders.get(row.order_id).push(row);
    }
    tickets.innerHTML = [...orders].map(([order, lines]) => {
      const items = lines.map(line => {
        const [status, label, action] = stages[line.status];
        return '<li class="kitchen-item"><div class="kitchen-item-copy"><strong>' +
          line.quantity + ' × ' + esc(names.get(line.dish_id) ?? "Dish #" + line.dish_id) +
          '</strong><p>' + esc(status) + (line.note ? ' · ' + esc(line.note) : '') + '</p></div>' +
          (action ? '<button type="button" class="kitchen-action" data-kitchen-item="' + line.order_item_id +
            '" data-kitchen-step="' + action + '">' + label + '</button>' : '') + '</li>';
      }).join("");
      return '<article class="kitchen-ticket" data-kitchen-ticket="' + order + '"><div class="kitchen-ticket-heading">' +
        '<h3>Order #' + order + '</h3></div><ul class="kitchen-item-list">' + items + '</ul></article>';
    }).join("") || '<p class="kitchen-empty">No orders in the preparation queue.</p>';
    find("[data-kitchen-count]").textContent = rows.length + (rows.length === 1 ? " item" : " items");
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
      const rows = view === "queue" ? (await Promise.all(Object.keys(stages).map(status =>
        restaurantRequest(restaurantQuery("/kitchen/queue", { status }))
      ))).flatMap(result => result.items) : [];
      if (current !== revision) return;
      if (view === "queue") renderQueue(rows, menuRows);
      else renderMenu(menuRows);
    } catch (error) {
      if (current === revision) feedback.textContent = error.message;
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
    button.disabled = true;
    feedback.textContent = "";
    try {
      if (kitchenItem) await restaurantRequest("/kitchen/items/" + kitchenItem + "/" + kitchenStep, {});
      else await restaurantRequest("/kitchen/menu/" + kitchenDish + "/availability", { is_available: kitchenNext });
      await refresh();
      const replacement = kitchenItem
        ? find('[data-kitchen-item="' + kitchenItem + '"]')
        : find('[data-kitchen-dish="' + kitchenDish + '"]');
      (replacement ?? find("[data-kitchen-refresh]")).focus();
    } catch (error) {
      feedback.textContent = error.message;
      if (error.status === 409) await refresh();
    } finally {
      button.disabled = false;
      pending = false;
    }
  });

  setInterval(() => {
    if (view === "queue" && !pending && !document.hidden && !tickets.contains(document.activeElement)) refresh();
  }, 8000);
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
