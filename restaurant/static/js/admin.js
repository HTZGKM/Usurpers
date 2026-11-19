function mountAdminWorkspace(workspace, tables, date, demo) {
  const find = (selector) => workspace.querySelector(selector);
  const sections = [...workspace.querySelectorAll("[data-admin-tab]")];
  const statuses = ["In queue", "Ready", "Served", "Cancelled"];
  const roles = { customer: "Customer", frontdesk: "Front desk", kitchen: "Kitchen" };
  const orderFilters = find("[data-admin-order-filters]");
  const tableFilters = find("[data-admin-table-filters]");
  const dialog = find(".admin-dialog");
  const accountForm = find("[data-admin-account-form]");
  const dishForm = find("[data-admin-dish-form]");
  const confirmForm = find("[data-admin-confirm]");
  const detail = find("[data-admin-detail]");
  const error = find("[data-admin-error]");
  let record;
  let confirmation;
  let selectedTable = "";
  const now = new Date(date + "T12:00:00");
  const todayLabel = find("[data-admin-today]");
  todayLabel.dateTime = date;
  todayLabel.textContent = now.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  tableFilters.querySelector("input").value = date;

  const payment = (order) => order.paidAt ? "Paid" : staffOrderStatus(order) === "Cancelled" ? "Not required" : "Unpaid";
  const dishStatus = (dish) => dish.archived ? "Archived" : dish.sold ? "Unavailable" : "Available";
  const cssTone = (status) => status.toLowerCase().replaceAll(" ", "-");
  const badge = (status) => '<span class="admin-badge" data-tone="' + cssTone(status) + '">' + esc(status) + '</span>';
  const action = (label, attribute, value, extra = "") => '<button type="button" class="admin-action' + extra +
    '" ' + attribute + '="' + esc(value) + '">' + esc(label) + '</button>';
  const byRecent = (a, b) => b.date.localeCompare(a.date) || b.time.localeCompare(a.time) || b.id - a.id;

  function table(headers, entries, empty) {
    if (!entries.length) return '<p class="admin-empty">' + esc(empty) + '</p>';
    return '<div class="admin-table-scroll"><table><thead><tr>' + headers.map((header) =>
      '<th scope="col">' + esc(header) + '</th>',
    ).join("") + '</tr></thead><tbody>' + entries.map((cells) => '<tr>' +
      cells.map((cell) => '<td>' + cell + '</td>').join("") + '</tr>',
    ).join("") + '</tbody></table></div>';
  }

  function orderTable(orders) {
    return table(["Order", "Table", "Date", "Status", "Payment", "Total"], orders.map((order) => [
      action("#" + order.id, "data-admin-order", order.id, " admin-order-link"),
      esc(order.table), esc(order.date + " · " + order.time), badge(staffOrderStatus(order)), badge(payment(order)),
      staffPrice(staffOrderTotal(order)),
    ]), "No matching orders.");
  }

  function roomStates(day, slot) {
    return tables.map(([id, capacity]) => ({ id, capacity,
      ...staffTableState(demo.reception, id, day, slot, date),
    }));
  }

  function renderOverview() {
    const ordersToday = demo.orders.filter((order) => order.date === date);
    const waiting = demo.orders.flatMap((order) => order.items).filter((item) => item.status === "Queued").length;
    const room = roomStates(date, "");
    const roomCount = (status) => room.filter((entry) => entry.status === status).length;
    const metrics = [
      ["Orders today", ordersToday.length, "orders"],
      ["Paid orders today", ordersToday.filter((order) => order.paidAt).length, "orders"],
      ["Items to prepare", waiting, "queue"],
      ["Occupied tables", roomCount("Occupied") + " / " + tables.length, "tables"],
    ];
    find("[data-admin-metrics]").innerHTML = metrics.map(([label, value, view]) =>
      '<button type="button" class="admin-metric" data-admin-go="' + view + '" data-metric="' + esc(label) + '">' +
      '<span>' + label + '</span><strong>' + value + '</strong><span class="admin-metric-arrow" aria-hidden="true">↗</span></button>',
    ).join("");
    find("[data-admin-order-chart-total]").textContent = ordersToday.length + " today";
    find("[data-admin-order-chart]").innerHTML = statuses.map((status) => {
      const count = ordersToday.filter((order) => staffOrderStatus(order) === status).length;
      const width = ordersToday.length ? 100 * count / ordersToday.length : 0;
      return '<button type="button" class="admin-chart-row" data-admin-chart-status="' + status +
        '" aria-label="' + esc(status + ": " + count + " orders today") + '"><span>' + status +
        '</span><span class="admin-chart-track" aria-hidden="true"><span data-tone="' + cssTone(status) +
        '" style="width:' + width + '%"></span></span><strong>' + count + '</strong></button>';
    }).join("");
    find("[data-admin-dining]").innerHTML = ["Available", "Reserved", "Occupied"].map((status) =>
      '<div><dt>' + badge(status) + '</dt><dd>' + roomCount(status) + '</dd></div>',
    ).join("");
    find("[data-admin-recent]").innerHTML = orderTable([...demo.orders].sort(byRecent).slice(0, 5));
  }

  function renderOrders() {
    const day = orderFilters.querySelector("[name=date]").value;
    const status = orderFilters.querySelector("[name=status]").value;
    const paid = orderFilters.querySelector("[name=payment]").value;
    const orders = demo.orders.filter((order) => (!day || order.date === day) &&
      (!status || staffOrderStatus(order) === status) && (!paid || payment(order) === paid)).sort(byRecent);
    find("[data-admin-order-list]").innerHTML = orderTable(orders);
  }

  function renderQueue() {
    const rows = [...demo.orders].sort((a, b) => -byRecent(a, b)).flatMap((order) =>
      order.items.filter((item) => item.status === "Queued").map((item) => [
        esc("#" + order.id), esc(order.table), esc(item.name), item.quantity, esc(item.note || "—"), esc(order.date + " · " + order.time),
      ]),
    );
    find("[data-admin-queue]").innerHTML = table(
      ["Order", "Table", "Dish", "Qty", "Kitchen note", "Placed"], rows, "No items awaiting preparation.",
    );
  }

  function renderTables() {
    const room = roomStates(tableFilters.querySelector("[name=date]").value || date,
      tableFilters.querySelector("[name=slot]").value);
    for (const entry of room) {
      const button = find('[data-desk-table="' + CSS.escape(entry.id) + '"]');
      button.dataset.tone = cssTone(entry.status);
      button.setAttribute("aria-label", "Table " + entry.id + ", " + entry.capacity + " seats, " + entry.status);
      button.setAttribute("aria-pressed", String(selectedTable === entry.id));
    }
    find("[data-admin-table-list]").innerHTML = '<ul class="admin-table-status">' + room.map((entry) =>
      '<li' + (selectedTable === entry.id ? ' data-selected' : '') + '><strong>' + esc(entry.id) +
      '</strong><span>' + entry.capacity + ' seats</span>' + badge(entry.status) + '</li>',
    ).join("") + '</ul>';
  }

  function renderAccounts() {
    const role = find("[data-admin-role]").value;
    const rows = demo.accounts.filter((account) => !role || account.role === role).map((account) => [
      esc(account.name), esc(roles[account.role]), esc(account.phone), esc(account.email || "—"),
      badge(account.active ? "Active" : "Inactive"),
      account.role === "customer" ? '<span class="admin-muted">Read only</span>' :
        '<div class="admin-row-actions">' + action("Edit", "data-admin-account", account.id) +
        (account.active ? action("Deactivate", "data-admin-deactivate", account.id) : "") + '</div>',
    ]);
    find("[data-admin-account-list]").innerHTML = table(
      ["Name", "Role", "Phone", "Email", "Status", "Actions"], rows, "No matching accounts.",
    );
  }

  function renderDishes() {
    const status = find("[data-admin-dish-filter]").value;
    const rows = demo.dishes.filter((dish) => !status || dishStatus(dish) === status).map((dish) => [
      esc(dish.name), esc(cats[dish.category]), staffPrice(dish.price), dish.minutes ? dish.minutes + " min" : "—",
      badge(dishStatus(dish)),
      '<div class="admin-row-actions">' + action("Edit", "data-admin-dish", dish.key) +
        (dish.archived ? "" : action("Archive", "data-admin-archive", dish.key)) + '</div>',
    ]);
    find("[data-admin-dish-list]").innerHTML = table(
      ["Dish", "Category", "Price", "Prep time", "Status", "Actions"], rows, "No matching dishes.",
    );
  }

  const renders = { overview: renderOverview, orders: renderOrders, queue: renderQueue,
    tables: renderTables, accounts: renderAccounts, dishes: renderDishes };
  function show(view, focus = true) {
    for (const button of sections) {
      const selected = button.dataset.adminTab === view;
      button.setAttribute("aria-pressed", String(selected));
      find("#" + button.getAttribute("aria-controls")).hidden = !selected;
      if (selected) find("[data-admin-title]").textContent = button.textContent.trim();
    }
    find("[data-admin-feedback]").hidden = true;
    renders[view]();
    if (focus) find("[data-admin-title]").focus();
  }

  function open(title, content, keepFocus = false) {
    for (const node of [accountForm, dishForm, detail, confirmForm]) node.hidden = node !== content;
    error.hidden = true;
    find("#admin-dialog-title").textContent = title;
    dialog.showModal();
    if (!keepFocus) content.querySelector("input:not(:disabled), button")?.focus();
  }

  function orderDetails(id) {
    const order = demo.orders.find((entry) => entry.id === Number(id));
    if (!order) return;
    detail.innerHTML = '<dl class="admin-order-summary">' + [
      ["Table", order.table], ["Placed", order.date + " · " + order.time],
      ["Status", staffOrderStatus(order)], ["Payment", payment(order)], ["Total", staffPrice(staffOrderTotal(order))],
    ].map(([label, value]) => '<div><dt>' + label + '</dt><dd>' + esc(value) + '</dd></div>').join("") + '</dl>' +
      table(["Dish", "Qty", "Unit price", "Kitchen note", "Status"], order.items.map((item) => [
        esc(item.name), item.quantity, staffPrice(item.price), esc(item.note || "—"), badge(item.status),
      ]), "No items.");
    open("Order #" + id, detail);
  }

  function openAccount(entry) {
    record = entry;
    accountForm.reset();
    const fields = accountForm.elements;
    find("[data-admin-password]").hidden = fields.password.disabled = Boolean(entry);
    if (entry) {
      fields.name.value = entry.name;
      fields.role.value = entry.role;
      fields.phone.value = entry.phone;
      fields.email.value = entry.email;
    }
    open(entry ? "Edit staff account" : "New staff account", accountForm, true);
    fields.name.focus();
  }

  function openDish(entry) {
    record = entry;
    dishForm.reset();
    if (entry) {
      const fields = dishForm.elements;
      fields.name.value = entry.name;
      fields.category.value = entry.category;
      fields.price.value = entry.price;
      fields.minutes.value = entry.minutes ?? "";
      fields.ingredients.value = entry.ingredients ?? entry.description ?? "";
      fields.image.value = entry.image ?? "";
    }
    open(entry ? "Edit dish" : "New dish", dishForm);
  }

  function confirmChange(type, entry) {
    record = entry;
    confirmation = type;
    const archive = type === "archive";
    find("[data-admin-confirm-copy]").textContent = archive
      ? "Archive " + entry.name + "? Existing orders will keep their original dish and price."
      : "Deactivate the demo account for " + entry.name + "?";
    find("[data-admin-confirm-submit]").textContent = archive ? "Archive dish" : "Deactivate account";
    open(archive ? "Archive dish" : "Deactivate account", confirmForm, true);
    find("[data-admin-close]").focus();
  }

  function notify(message) {
    saveStaffDemo(demo);
    dialog.close();
    const feedback = find("[data-admin-feedback]");
    feedback.textContent = message;
    feedback.hidden = false;
    feedback.tabIndex = -1;
    feedback.focus({ preventScroll: true });
  }

  function fail(message) {
    error.textContent = message;
    error.hidden = false;
  }

  accountForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const fields = accountForm.elements;
    const name = fields.name.value.trim();
    const phone = fields.phone.value.trim();
    const email = fields.email.value.trim().toLowerCase();
    if (!name || !/^\+?\d+$/.test(phone) || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      fail("Enter a name, a valid email address and a phone number.");
      return;
    }
    if (demo.accounts.some((entry) => entry !== record && entry.role !== "customer" &&
        (entry.email === email || entry.phone === phone))) {
      fail("A staff account already uses this email address or phone number.");
      return;
    }
    const changes = { name, email, phone, role: fields.role.value };
    if (record) Object.assign(record, changes);
    else demo.accounts.push({ ...changes, id: Math.max(0, ...demo.accounts.map((entry) => entry.id)) + 1, active: true });
    fields.password.value = "";
    find("[data-admin-role]").value = changes.role;
    renderAccounts();
    notify(record ? "Staff account updated." : "Demo staff account created.");
  });

  dishForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const fields = dishForm.elements;
    const name = fields.name.value.trim();
    const ingredients = fields.ingredients.value.trim();
    if (!name || !ingredients) {
      fail("Enter a dish name and its ingredients.");
      return;
    }
    if (demo.dishes.some((entry) => entry !== record && entry.name.toLowerCase() === name.toLowerCase())) {
      fail("A dish already uses this name.");
      return;
    }
    const changes = { name, ingredients, category: fields.category.value, price: fields.price.valueAsNumber,
      minutes: fields.minutes.valueAsNumber, image: fields.image.value.trim() };
    if (record) Object.assign(record, changes);
    else demo.dishes.push({ ...changes, key: "staff-dish-" + (demo.dishes.length + 1), sold: false });
    find("[data-admin-dish-filter]").value = "";
    renderDishes();
    notify(record ? "Dish updated." : "Dish added.");
  });

  confirmForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (confirmation === "archive") {
      record.archived = true;
      find("[data-admin-dish-filter]").value = "Archived";
      renderDishes();
      notify("Dish archived.");
    } else {
      record.active = false;
      renderAccounts();
      notify("Demo staff account deactivated.");
    }
  });
  dialog.addEventListener("close", () => { accountForm.elements.password.value = ""; });
  dialog.addEventListener("input", () => { error.hidden = true; });
  orderFilters.addEventListener("change", renderOrders);
  tableFilters.addEventListener("change", renderTables);
  find("[data-admin-role]").addEventListener("change", renderAccounts);
  find("[data-admin-dish-filter]").addEventListener("change", renderDishes);

  workspace.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const data = button.dataset;
    const view = data.adminTab ?? data.adminGo;
    if (view === "orders" && data.adminGo) {
      orderFilters.querySelector("[name=date]").value = data.metric ? date : "";
      orderFilters.querySelector("[name=status]").value = "";
      orderFilters.querySelector("[name=payment]").value = data.metric === "Paid orders today" ? "Paid" : "";
    }
    if (view) show(view);
    else if (data.adminChartStatus) {
      orderFilters.querySelector("[name=date]").value = date;
      orderFilters.querySelector("[name=status]").value = data.adminChartStatus;
      orderFilters.querySelector("[name=payment]").value = "";
      show("orders");
    } else if (data.adminOrder) orderDetails(data.adminOrder);
    else if (data.deskTable) {
      selectedTable = data.deskTable;
      renderTables();
    } else if (data.adminEdit === "account") openAccount();
    else if (data.adminEdit === "dish") openDish();
    else if (data.adminAccount || data.adminDeactivate) {
      const entry = demo.accounts.find((account) => account.id === Number(data.adminAccount ?? data.adminDeactivate));
      if (!entry || entry.role === "customer") return;
      if (data.adminDeactivate && entry.active) confirmChange("deactivate", entry);
      else if (data.adminAccount) openAccount(entry);
    } else if (data.adminDish || data.adminArchive) {
      const entry = demo.dishes.find((dish) => dish.key === (data.adminDish ?? data.adminArchive));
      if (!entry) return;
      if (data.adminArchive && !entry.archived) confirmChange("archive", entry);
      else if (data.adminDish) openDish(entry);
    } else if ("adminClose" in data) dialog.close();
  });

  show("overview", false);
}
