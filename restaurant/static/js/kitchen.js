function mountKitchenWorkspace(workspace, username, demo) {
  if (!demo.kitchenMigrated) {
    const previous = readStaffPreview("double-portion-kitchen-preview-v1." + username);
    const completed = new Set(previous?.completed ?? []);
    const availability = new Map(previous?.availability ?? []);
    for (const order of demo.orders) {
      for (const item of order.items) {
        if (item.status === "Queued" && completed.has(order.id + "-" + item.id)) item.status = "Ready";
      }
    }
    for (const dish of demo.dishes) {
      if (availability.has(dish.key)) dish.sold = !availability.get(dish.key);
    }
    demo.kitchenMigrated = true;
    saveStaffDemo(demo);
  }

  const queueCount = workspace.querySelector("[data-kitchen-count]");
  const tickets = workspace.querySelector("[data-kitchen-tickets]");

  function renderQueue() {
    let pending = 0;
    tickets.innerHTML = demo.orders.map((order) => {
      const items = order.items.filter((item) => item.status === "Queued" || item.status === "Ready");
      if (!items.length) return "";
      const ready = items.every((item) => item.status === "Ready");
      return '<article class="kitchen-ticket" data-kitchen-ticket="' + order.id + '" aria-labelledby="kitchen-order-' + order.id + '">' +
        '<div class="kitchen-ticket-heading"><div><p class="kitchen-order-number" id="kitchen-order-' + order.id + '">' +
        'Order #' + order.id + '</p><h3>Table ' + esc(order.table) + '</h3></div><span class="kitchen-status" data-tone="' +
        (ready ? 'done">Ready' : 'waiting">In queue') + '</span></div><ul class="kitchen-item-list">' +
        items.map((item) => {
          const done = item.status === "Ready";
          pending += Number(!done);
          return '<li class="kitchen-item' + (done ? ' is-complete' : '') + '" data-kitchen-item="' + item.id +
            '"><div class="kitchen-item-copy"><strong>' + item.quantity + ' × ' + esc(item.name) + '</strong>' +
            (item.note ? '<p>' + esc(item.note) + '</p>' : '') + '</div><button type="button" class="kitchen-action" data-complete="' +
            item.id + '" aria-label="' + esc(done ? item.name + " completed" : "Complete " + item.name + " for table " + order.table) +
            '"' + (done ? ' disabled>Completed' : '>Complete') + '</button></li>';
        }).join("") + '</ul></article>';
    }).join("");
    queueCount.textContent = pending === 0 ? "All items completed" : pending === 1 ? "1 item to prepare" : pending + " items to prepare";
  }

  function renderAvailability() {
    for (const group of workspace.querySelectorAll("[data-kitchen-category]")) {
      group.innerHTML = demo.dishes.filter((dish) => !dish.archived && dish.category === group.dataset.kitchenCategory)
        .map((dish) => {
          const action = dish.sold ? "Mark available" : "Mark unavailable";
          return '<li class="kitchen-item" data-kitchen-dish="' + esc(dish.key) + '"><div class="kitchen-item-copy"><strong>' +
            esc(dish.name) + '</strong><span class="kitchen-status" data-tone="' + (dish.sold ? 'waiting">Unavailable' : 'done">Available') +
            '</span></div><button type="button" class="kitchen-action" data-toggle-availability aria-label="' +
            esc(action + ": " + dish.name) + '">' + action + '</button></li>';
        }).join("") || '<li class="kitchen-item">No listed dishes.</li>';
    }
    workspace.querySelector("[data-availability-count]").textContent =
      demo.dishes.filter((dish) => !dish.archived && dish.sold).length + " unavailable";
  }

  workspace.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    const view = button.dataset.kitchenView;
    if (view) {
      for (const tab of workspace.querySelectorAll("[data-kitchen-view]")) {
        const active = tab.dataset.kitchenView === view;
        tab.setAttribute("aria-pressed", String(active));
        workspace.querySelector("#" + tab.getAttribute("aria-controls")).hidden = !active;
      }
    } else if (button.matches("[data-complete]")) {
      const order = demo.orders.find((entry) => entry.id === Number(button.closest("[data-kitchen-ticket]").dataset.kitchenTicket));
      const item = order?.items.find((entry) => entry.id === Number(button.dataset.complete));
      if (item?.status !== "Queued") return;
      item.status = "Ready";
      saveStaffDemo(demo);
      renderQueue();
      (workspace.querySelector("[data-complete]:enabled") ?? queueCount).focus({ preventScroll: true });
    } else if (button.matches("[data-toggle-availability]")) {
      const key = button.closest("[data-kitchen-dish]").dataset.kitchenDish;
      const dish = demo.dishes.find((entry) => entry.key === key);
      if (!dish || dish.archived) return;
      dish.sold = !dish.sold;
      saveStaffDemo(demo);
      renderAvailability();
      workspace.querySelector('[data-kitchen-dish="' + CSS.escape(key) + '"] button')?.focus();
    }
  });

  renderQueue();
  renderAvailability();
}
