function mountFrontdeskWorkspace(workspace, navigate) {
  const find = (selector) => workspace.querySelector(selector);
  const dateFilter = find("[data-desk-view-date]");
  const slotFilter = find("[data-desk-slot]");
  const phoneFilter = find("[data-desk-search]");
  const dialog = find(".desk-dialog");
  const editor = find("[data-desk-editor]");
  const walkIn = find("[data-desk-walk-in]");
  const cancellation = find("[data-desk-cancellation]");
  const serviceForm = find("[data-service-form]");
  const checkIn = find("[data-desk-check-in]");
  const callForm = find("[data-desk-call]");
  const feedback = find("[data-desk-floor-feedback]");
  const workspaceNotice = find("[data-desk-live-notice]");
  const syncNotice = find("[data-desk-sync]");
  let view = "reservations";
  let bookingId;
  let tableId;
  let visitId;
  let dialogMode;
  let bookings = [];
  let occupancy = [];
  let visits = [];
  let queue = [];
  let freeTables = [];
  let serviceMenu = [];
  let serviceOrders = [];
  let draft = [];
  let revision = 0;
  let pending = false;
  let polling = false;
  let filtersTimer;
  let todaysArrivals = 0;
  let focusReadyOrder = false;

  dateFilter.value = today();
  find("[data-desk-date]").textContent = today();
  const chosenBooking = () => bookings.find(row => row.booking_id === bookingId);
  const chosenVisit = () => visits.find(row => row.visit_id === visitId && row.status === "seated");
  const fieldValues = (form) => Object.fromEntries([...new FormData(form)].filter(([, value]) => value !== ""));
  const option = (value, label) => '<option value="' + value + '">' + esc(label) + '</option>';
  const deskButton = (label, attrs) => '<button type="button" class="desk-subtle" ' + attrs + '>' + label + '</button>';
  const readyVisits = () => visits.filter(row => row.status === "seated" && row.ready_count > 0)
    .sort((a, b) => a.table_id - b.table_id);
  const readyDishes = (count) => count + (count === 1 ? " dish ready" : " dishes ready");
  const hasReadyItems = (order) => order.items.some(item => item.status === "ready");

  function replaceList(target, markup, background) {
    if (target.innerHTML === markup) return;
    const focused = document.activeElement;
    const hasFocus = target.contains(focused);
    const key = hasFocus && focused.matches("button") && !focused.closest("form") ? Object.keys(focused.dataset)[0] : null;
    if (background && hasFocus && !key) return;
    target.innerHTML = markup;
    if (key) Array.from(target.querySelectorAll("button")).find(button =>
      button.dataset[key] === focused.dataset[key])?.focus({ preventScroll: true });
  }

  function renderTasks() {
    const counts = {
      ready: readyVisits().reduce((sum, row) => sum + row.ready_count, 0),
      arrivals: todaysArrivals,
      waitlist: queue.length,
    };
    for (const task of workspace.querySelectorAll("[data-desk-task]")) {
      const count = counts[task.dataset.deskTask];
      task.querySelector("strong").textContent = count;
      task.disabled = !count;
    }
    const tableCount = readyVisits().length;
    find("[data-desk-ready-tables]").textContent = tableCount
      ? tableCount + (tableCount === 1 ? " table" : " tables") : "";
  }

  function setTableOptions(select, rows, selected) {
    select.innerHTML = rows.map(row => option(row.table_id, tableLabel(row.table_id) + " · " + row.capacity + " seats")).join("");
    if (rows.some(row => row.table_id === selected)) select.value = selected;
  }

  function renderReception(background = false) {
    const visible = bookings.filter(row => !phoneFilter.value.trim() ||
      row.phone_number.includes(phoneFilter.value.trim())).sort((a, b) => (b.status === "booked") - (a.status === "booked"));
    replaceList(find("[data-desk-bookings]"), visible.map(row =>
      '<li><button type="button" class="desk-booking" data-desk-booking="' + row.booking_id +
      '" aria-pressed="' + (row.booking_id === bookingId) + '"><span class="desk-booking-guest"><strong>' + esc(row.contact_name) +
      '</strong><small>' + esc(row.phone_number) + '</small></span><span class="desk-booking-time">' +
      esc(row.time_slot) + ' · ' + esc(tableLabel(row.table_id) || "Unassigned") + '</span><span class="desk-chip" data-tone="' +
      (row.status === "booked" ? "reserved" : row.status === "arrived" ? "available" : "cancelled") + '">' +
      esc(bookingLabels[row.status] ?? row.status) + '</span></button></li>'
    ).join(""), background);
    find("[data-desk-empty]").hidden = visible.length > 0;
    find("[data-desk-booking-count]").textContent = visible.length + " reservations";
    find("[data-desk-occupied]").textContent = occupancy.filter(table => table.status === "occupied").length +
      " / " + occupancy.length + " occupied";
    for (const tile of workspace.querySelectorAll("[data-desk-table]")) {
      const id = tableIds[tile.dataset.deskTable];
      const row = occupancy.find(table => table.table_id === id);
      tile.dataset.tone = row?.status ?? "available";
      const tableStatus = tile.dataset.tone;
      const status = tile.querySelector("small");
      status.textContent = tableStatus[0].toUpperCase() + tableStatus.slice(1);
      tile.setAttribute("aria-label", "Table " + tile.dataset.deskTable + " · " + status.textContent +
        (row?.capacity ? " · " + row.capacity + " seats" : ""));
      tile.setAttribute("aria-pressed", id === tableId);
    }
    const selectedTable = occupancy.find(table => table.table_id === tableId);
    find('[data-desk-open="walk-in"]').hidden = selectedTable?.status !== "available";
    find('[data-desk-open="service"]').hidden = !visits.some(row => row.table_id === tableId && row.status === "seated");
    const row = chosenBooking();
    find("[data-desk-arrival-copy]").textContent = row
      ? row.contact_name + " · " + (bookingLabels[row.status] ?? row.status) + " · " + (tableLabel(row.table_id) || "Unassigned")
      : "Select a reservation to check in the guest.";
    const canEdit = row?.status === "booked";
    const canCheckIn = canEdit && row.booking_date === today();
    checkIn.hidden = !canCheckIn;
    find("[data-desk-booking-actions]").hidden = !canEdit;
    if (canEdit && !canCheckIn) find("[data-desk-arrival-copy]").textContent += " · Check-in opens on the booking date.";
    if (canCheckIn) {
      const available = occupancy.filter(table => table.capacity >= row.party_size &&
        (table.status === "available" || (table.status === "reserved" && table.table_id === row.table_id)));
      const selection = checkIn.dataset.booking === String(row.booking_id) ? Number(checkIn.elements.table_id.value) : row.table_id;
      if (!background || !checkIn.contains(document.activeElement)) {
        setTableOptions(checkIn.elements.table_id, available, selection);
        checkIn.dataset.booking = row.booking_id;
      }
      checkIn.querySelector("[type=submit]").disabled = available.length === 0;
    }
  }

  function renderDraft() {
    find("[data-service-draft]").innerHTML = draft.map((line, index) =>
      '<li><span>' + line.quantity + ' × ' + esc(line.name) + (line.note ? ' · ' + esc(line.note) : '') +
      '</span>' + deskButton("Remove", 'data-draft-remove="' + index + '"') + '</li>').join("");
    find("[data-place-desk-order]").disabled = !draft.length;
  }

  function renderWaitlist(background = false) {
    const select = callForm.elements.table_id;
    if (!background || !callForm.contains(document.activeElement)) setTableOptions(select, freeTables, Number(select.value));
    select.disabled = !freeTables.length;
    callForm.querySelector("[type=submit]").disabled = !freeTables.length || !queue.some(row => row.status === "waiting");
    find("[data-desk-waiting-empty]").hidden = queue.length > 0;
    replaceList(find("[data-desk-waiting-list]"), queue.map(row => {
      const called = row.status === "called";
      const chairs = Math.max(row.party_size, row.table_type || 0);
      const choices = row.called_table_id
        ? option(row.called_table_id, tableLabel(row.called_table_id))
        : freeTables.filter(table => table.capacity >= chairs).map(table => option(table.table_id, tableLabel(table.table_id))).join("");
      return '<li><span><strong>Ticket #' + row.queue_id + '</strong> · ' + esc(row.contact_name || "Walk-in") +
        ' · ' + row.party_size + ' guests · ' + (called ? "Called" : "Waiting") + '</span>' +
        (called && choices ? '<form class="desk-check-in" data-seat-ticket="' + row.queue_id +
          '"><label>Table <select name="table_id" required>' + choices +
          '</select></label><button type="submit" class="desk-confirm">Seat party</button></form>' : '') + '</li>';
    }).join(""), background);
  }

  function orderCard(order) {
    const items = [...order.items].sort((a, b) => Number(b.status === "ready") - Number(a.status === "ready")).map(item => {
      const path = "/frontdesk/orders/" + order.order_id + "/items/" + item.order_item_id;
      return '<li data-item-stage="' + esc(item.status) + '"><div><strong>' + item.quantity + ' × ' + esc(item.dish_name) +
        '</strong><span class="desk-item-status">' +
        esc({ waiting: "Waiting", cooking: "Cooking", ready: "Ready to serve", served: "Served", cancelled: "Cancelled" }[item.status] ?? item.status) +
        '</span>' + (item.note ? '<small>' + esc(item.note) + '</small>' : '') + '</div>' +
        (item.status === "ready" ? '<button type="button" class="desk-confirm" data-desk-write="' + path + '/serve">Mark served</button>' :
          item.status === "waiting" && order.payment_status === "unpaid"
            ? deskButton("Cancel item", 'data-desk-write="' + path + '/cancel"') : '') + '</li>';
    }).join("");
    return '<article class="desk-service-order" data-service-order="' + order.order_id + '" data-ready="' + hasReadyItems(order) + '"><h4 tabindex="-1">' +
      (order.order_type === "preorder" ? "Preorder #" : "Order #") +
      order.order_id + ' · ¥' + esc(order.total_amount) + '</h4><p>' +
      esc(orderLabels[order.status] ?? order.status) + ' · ' +
      (order.payment_status === "paid" ? "Paid" : "Unpaid") + '</p><ul class="desk-service-list">' +
      items + '</ul>' + (restaurantCanEditOrder(order) ?
        deskButton("Edit order", 'data-desk-edit-order="' + order.order_id + '"') : '') +
      (order.payment_status === "unpaid" && order.status !== "cancelled"
        ? deskButton("Record payment", 'data-desk-write="/frontdesk/orders/' + order.order_id + '/pay"') : '') + '</article>';
  }

  function renderBilling(orders) {
    find("[data-desk-billing-list]").innerHTML = orders.map(row =>
      '<details class="desk-service-order" data-billing-order="' + row.order_id + '"><summary>Order #' +
      row.order_id + ' · ' + esc(tableLabel(row.table_id) || "No table") + ' · ' +
      (row.payment_status === "paid" ? "Paid" : "Unpaid") + '</summary><div data-billing-detail></div></details>'
    ).join("") || "<p>No orders found.</p>";
  }

  function renderCloseControls(orders) {
    let message = "";
    if (!orders) message = "Checking whether this table can be released…";
    else if (orders.some(order => order.status !== "cancelled" && order.payment_status !== "paid")) {
      message = "Settle all open orders before releasing this table.";
    } else if (orders.some(order => order.items.some(item => !["served", "cancelled"].includes(item.status)))) {
      message = "Serve all remaining dishes before releasing this table.";
    }
    const releaseNotice = find("[data-service-feedback]");
    if (releaseNotice.textContent !== message) releaseNotice.textContent = message;
    find("[data-close-desk-visit]").disabled = Boolean(message);
    find("[data-release-desk-table]").disabled = Boolean(message);
    if (message) find("[data-confirm-desk-close]").hidden = true;
  }

  function selectServiceVisit(next) {
    if (visitId === next) return;
    visitId = next;
    draft = [];
    serviceForm.reset();
    serviceOrders = [];
    find("[data-service-orders]").textContent = "Loading orders…";
    find("[data-confirm-desk-close]").hidden = true;
  }

  const canPoll = () => !pending && !document.hidden && view !== "billing" && !document.querySelector("dialog[open]");

  async function refresh(background = false) {
    const current = ++revision;
    if (view === "reservations") {
      const filters = { date: dateFilter.value };
      if (slotFilter.value) filters.time_slot_id = slotFilter.value;
      const occupancySlot = chosenBooking()?.time_slot;
      const slot = slotFilter.value || Object.keys(slots).find(key => slots[key] === occupancySlot) || "2";
      const listRequest = restaurantRequest(restaurantQuery("/frontdesk/bookings", filters));
      const todayRequest = filters.date === today() && !filters.time_slot_id ? listRequest :
        restaurantRequest(restaurantQuery("/frontdesk/bookings", { date: today() }));
      const [list, floor, seating, waiting, todayList] = await Promise.all([
        listRequest,
        restaurantRequest(restaurantQuery("/frontdesk/tables", { date: filters.date, time_slot_id: slot })),
        restaurantSeating(),
        restaurantRequest("/frontdesk/waiting-queue"),
        todayRequest,
      ]);
      if (current !== revision || (background && !canPoll())) return;
      bookings = list.bookings;
      todaysArrivals = todayList.bookings.filter(row => row.status === "booked").length;
      occupancy = floor.tables;
      visits = seating;
      queue = waiting.queue;
      freeTables = waiting.tables;
      renderTasks();
      renderReception(background);
      renderWaitlist(background);
    } else if (view === "service") {
      if (!background) renderCloseControls(null);
      const [seating, waiting] = await Promise.all([restaurantSeating(), restaurantRequest("/frontdesk/waiting-queue")]);
      if (current !== revision || (background && !canPoll())) return;
      visits = seating;
      const unassigned = visits.filter(row => row.status === "waiting");
      replaceList(find("[data-desk-unassigned]"), unassigned.map(row =>
        '<form class="desk-check-in" data-assign-visit="' + row.visit_id + '"><span>' + esc(row.contact_name || "Walk-in") +
        '</span><label>Table <select name="table_id" required>' +
        waiting.tables.filter(table => table.capacity >= row.party_size).map(table => option(table.table_id, tableLabel(table.table_id))).join("") +
        '</select></label><button type="submit" class="desk-confirm">Assign table</button></form>'
      ).join(""), background);
      const seated = visits.filter(row => row.status === "seated").sort((a, b) =>
        Number(b.ready_count > 0) - Number(a.ready_count > 0) || a.table_id - b.table_id);
      replaceList(find("[data-desk-service-picker]"), seated.map(row =>
        '<button type="button" class="desk-table-card" data-live-visit="' + row.visit_id +
        '" data-ready="' + Boolean(row.ready_count) + '" aria-pressed="' + (visitId === row.visit_id) +
        '"><span class="desk-table-card-top"><strong>' + esc(tableLabel(row.table_id)) + '</strong>' +
        '<span>' + row.party_size + (row.party_size === 1 ? ' guest' : ' guests') + '</span></span>' +
        '<span class="desk-table-guest">' + esc(row.contact_name || "Walk-in") + '</span>' +
        '<span class="desk-table-status">' + (row.ready_count ? readyDishes(row.ready_count) :
          row.unpaid_count ? "Payment due" : "In service") + '</span></button>'
      ).join("") || "<p>No guests are seated.</p>", background);
      const totalReady = seated.reduce((sum, row) => sum + row.ready_count, 0);
      find("[data-desk-service-count]").textContent = seated.length + " occupied · " + readyDishes(totalReady);
      const visit = chosenVisit();
      find("[data-desk-service]").hidden = !visit;
      find("[data-desk-choose-table]").hidden = Boolean(visit) || !seated.length;
      if (!visit) {
        focusReadyOrder = false;
        syncNotice.textContent = "Auto-updates on";
        return;
      }
      find("[data-service-visit]").textContent = "Table " + tableLabel(visit.table_id);
      const [menuData, orderData] = await Promise.all([
        restaurantRequest("/frontdesk/menu"),
        restaurantRequest(restaurantQuery("/frontdesk/orders", { table_id: visit.table_id })),
      ]);
      const orders = await Promise.all(orderData.orders.filter(row => row.visit_id === visit.visit_id)
        .map(row => restaurantRequest("/frontdesk/orders/" + row.order_id)));
      if (current !== revision || (background && !canPoll())) return;
      serviceMenu = menuData.items;
      serviceOrders = orders.map(result => result.order)
        .sort((a, b) => Number(hasReadyItems(b)) - Number(hasReadyItems(a)));
      const dishField = serviceForm.elements.dish;
      const selected = dishField.value;
      replaceList(dishField, menuData.items.map(row => option(row.dish_id, row.dish_name + " · ¥" + row.price)).join(""), background);
      if (menuData.items.some(row => row.dish_id === Number(selected))) dishField.value = selected;
      serviceForm.querySelector("[type=submit]").disabled = !menuData.items.length;
      if (!background) renderDraft();
      replaceList(find("[data-service-orders]"), serviceOrders.map(orderCard).join("") || "<p>No orders for this visit.</p>", background);
      if (focusReadyOrder) {
        focusReadyOrder = false;
        (find('[data-service-order][data-ready="true"] h4') ?? find("#desk-service-title")).focus();
      }
      renderCloseControls(serviceOrders);
    } else {
      const { orders } = await restaurantRequest("/frontdesk/orders");
      if (current === revision) renderBilling(orders);
    }
    if (current === revision) syncNotice.textContent = view === "billing" ? "" : "Auto-updates on";
  }

  async function update(work) {
    if (pending) return;
    pending = true;
    ++revision;
    workspaceNotice.textContent = "";
    try {
      const message = await work();
      if (message) workspaceNotice.textContent = message;
      await refresh();
    } catch (error) {
      workspaceNotice.textContent = error.message;
      if (dialog.open) {
        const errorField = dialog.querySelector("form:not([hidden]) [role=alert]");
        if (errorField) {
          errorField.hidden = false;
          errorField.textContent = error.message;
        }
      }
    } finally {
      pending = false;
    }
  }

  function openDialog(mode) {
    const booking = chosenBooking();
    dialogMode = mode;
    editor.hidden = !["new", "edit"].includes(mode);
    walkIn.hidden = mode !== "walk-in";
    cancellation.hidden = mode !== "cancel";
    find("[data-desk-dialog-copy]").hidden = !["walk-in", "cancel"].includes(mode);
    find("[data-desk-dialog-copy]").textContent = mode === "walk-in"
      ? "Table " + tableLabel(tableId) : "Release the table for this reservation?";
    find("#desk-dialog-title").textContent = {
      new: "New booking", edit: "Edit booking", "walk-in": "Seat walk-in", cancel: "Cancel booking",
    }[mode];
    for (const error of dialog.querySelectorAll("[role=alert]")) {
      error.hidden = true;
      error.textContent = "";
    }
    if (!editor.hidden) {
      editor.reset();
      editor.elements.booking_date.value = mode === "edit" ? booking.booking_date : dateFilter.value;
      editor.elements.time_slot_id.value = mode === "edit"
        ? Object.keys(slots).find(key => slots[key] === booking.time_slot) : slotFilter.value || "2";
      editor.elements.party_size.value = mode === "edit" ? booking.party_size : 2;
      editor.elements.table_id.value = mode === "edit" ? booking.table_id ?? "" : "";
      editor.elements.contact_name.value = mode === "edit" ? booking.contact_name : "";
      editor.elements.phone_number.value = mode === "edit" ? booking.phone_number : "";
      editor.elements.contact_name.readOnly = mode === "edit";
      editor.elements.phone_number.readOnly = mode === "edit";
    }
    if (mode === "walk-in") walkIn.reset();
    dialog.showModal();
  }

  workspace.addEventListener("submit", (event) => {
    const form = event.target;
    if (![editor, checkIn, walkIn, cancellation, serviceForm, callForm].includes(form) &&
      !form.matches("[data-seat-ticket],[data-assign-visit]")) return;
    event.preventDefault();
    if (pending) return;
    const fields = fieldValues(form);
    if (form === callForm) return update(async () => {
      const { queue } = await restaurantRequest("/frontdesk/tables/" + fields.table_id + "/call-next", {});
      return queue ? "Ticket #" + queue.queue_id + " called for table " + tableLabel(queue.table_id) + "." :
        "No waiting party fits this table.";
    });
    if (form.matches("[data-seat-ticket],[data-assign-visit]")) return update(async () => {
      if (!fields.table_id) return "No suitable table is available.";
      const path = form.dataset.seatTicket ? "/frontdesk/waiting-queue/" + form.dataset.seatTicket + "/seat" :
        "/frontdesk/visits/" + form.dataset.assignVisit + "/assign";
      const { visit } = await restaurantRequest(path, fields);
      tableId = visit.table_id;
      selectServiceVisit(visit.visit_id);
      return "Guests seated at " + tableLabel(tableId) + ".";
    });
    if (form === serviceForm) {
      const dish = serviceForm.elements.dish.selectedOptions[0];
      draft.push({ dishId: Number(fields.dish), quantity: Number(fields.quantity), note: fields.note ?? "",
        name: dish.textContent.split(" · ¥")[0] });
      serviceForm.elements.note.value = "";
      renderDraft();
      return;
    }
    if (form === editor) update(async () => {
      const path = dialogMode === "edit" ? "/frontdesk/bookings/" + bookingId + "/edit" : "/frontdesk/bookings";
      const { booking } = await restaurantRequest(path, fields);
      bookingId = booking.booking_id;
      dateFilter.value = fields.booking_date;
      dialog.close();
      return "Reservation saved.";
    });
    if (form === cancellation) update(async () => {
      await restaurantRequest("/frontdesk/bookings/" + bookingId + "/cancel", {});
      dialog.close();
      return "Reservation cancelled.";
    });
    if (form === checkIn || form === walkIn) update(async () => {
      const path = form === checkIn ? "/frontdesk/bookings/" + bookingId + "/check-in" : "/frontdesk/walk-ins";
      if (form === walkIn) fields.table_id = tableId;
      const { visit } = await restaurantRequest(path, fields);
      tableId = visit.table_id;
      selectServiceVisit(visit.visit_id);
      if (dialog.open) dialog.close();
      return "Guests seated at " + tableLabel(visit.table_id) + ".";
    });
  });

  workspace.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled || pending) return;
    const data = button.dataset;
    if (button.matches("[data-desk-refresh]")) return update(async () => "");
    if (button.matches("[data-desk-close]")) return dialog.close();
    if (data.deskTask === "ready") {
      selectServiceVisit(readyVisits()[0]?.visit_id);
      focusReadyOrder = true;
      return navigate("service");
    }
    if (data.deskTask) {
      if (data.deskTask === "arrivals" && (dateFilter.value !== today() || slotFilter.value || phoneFilter.value)) {
        dateFilter.value = today();
        slotFilter.value = phoneFilter.value = "";
        bookingId = undefined;
        update(async () => "");
      }
      const target = find(data.deskTask === "arrivals" ? "#desk-bookings-title" : "#desk-waitlist-title");
      target.focus();
      target.scrollIntoView({ block: "start" });
      return;
    }
    if (data.deskBooking) {
      bookingId = Number(data.deskBooking);
      tableId = chosenBooking()?.table_id;
      renderReception();
      return update(async () => "");
    }
    if (data.deskTable) {
      tableId = tableIds[data.deskTable];
      feedback.textContent = "Table " + data.deskTable;
      return renderReception();
    }
    if (data.deskOpen === "service") {
      selectServiceVisit(visits.find(row => row.table_id === tableId && row.status === "seated")?.visit_id);
      return navigate("service");
    }
    if (data.deskOpen) return openDialog(data.deskOpen);
    if (data.liveVisit) {
      focusReadyOrder = false;
      selectServiceVisit(Number(data.liveVisit));
      return update(async () => "");
    }
    if (data.draftRemove !== undefined) {
      draft.splice(Number(data.draftRemove), 1);
      return renderDraft();
    }
    if (data.deskEditOrder) {
      const order = serviceOrders.find(row => row.order_id === Number(data.deskEditOrder));
      if (order) restaurantOrderEditor(order, "/frontdesk/orders/" + order.order_id + "/edit", serviceMenu,
        () => update(async () => "Order updated."));
      return;
    }
    if (button.matches("[data-place-desk-order]")) return update(async () => {
      const { order } = await restaurantRequest("/frontdesk/orders", { visit_id: visitId, ...restaurantOrderFields(draft) });
      draft = [];
      renderDraft();
      return "Order #" + order.order_id + " sent to the kitchen.";
    });
    if (data.deskWrite) return update(async () => {
      const table = tableLabel(chosenVisit()?.table_id);
      await restaurantRequest(data.deskWrite, {});
      if (data.deskWrite.endsWith("/serve")) return "Dish served" + (table ? " at table " + table : "") + ".";
      return data.deskWrite.endsWith("/pay") ? "Payment recorded." : "Item cancelled.";
    });
    const closeConfirmation = find("[data-confirm-desk-close]");
    if (button.matches("[data-close-desk-visit],[data-keep-desk-visit]")) {
      closeConfirmation.hidden = button.matches("[data-keep-desk-visit]");
    }
    if (button.matches("[data-release-desk-table]")) return update(async () => {
      const { visit } = await restaurantRequest("/frontdesk/visits/" + visitId + "/close", {});
      selectServiceVisit(undefined);
      return visit.next_queue ? "Table released. Ticket #" + visit.next_queue.queue_id + " was called." : "Table released.";
    });
  });

  workspace.addEventListener("toggle", async (event) => {
    const record = event.target;
    if (!record.matches("[data-billing-order][open]") || record.dataset.loaded) return;
    const detail = record.querySelector("[data-billing-detail]");
    detail.textContent = "Loading order…";
    try {
      const { order } = await restaurantRequest("/frontdesk/orders/" + record.dataset.billingOrder);
      detail.innerHTML = '<p>Total · ¥' + esc(order.total_amount) + '</p><ul class="desk-service-list">' +
        order.items.map(item => '<li>' + item.quantity + ' × ' + esc(item.dish_name) + '</li>').join("") + '</ul>';
      record.dataset.loaded = "true";
    } catch (error) {
      detail.textContent = error.message;
    }
  }, true);

  for (const field of [dateFilter, slotFilter]) field.addEventListener("change", () => {
    bookingId = undefined;
    if (dateFilter.value) update(async () => "");
  });
  phoneFilter.addEventListener("input", () => {
    clearTimeout(filtersTimer);
    filtersTimer = setTimeout(renderReception, 100);
  });

  async function poll() {
    if (polling || !canPoll()) return;
    polling = true;
    try {
      await refresh(true);
    } catch (error) {
      if (canPoll()) syncNotice.textContent = "Updates paused · Refresh";
    } finally {
      polling = false;
    }
  }
  setInterval(poll, 3000);
  document.addEventListener("visibilitychange", poll);

  return (section, focus) => {
    if (view !== section) workspaceNotice.textContent = "";
    view = section;
    if (view !== "service") focusReadyOrder = false;
    const sections = { reservations: find("[data-desk-reception]"), service: find("[data-desk-service-view]"),
      billing: find("[data-desk-billing]") };
    for (const [key, panel] of Object.entries(sections)) panel.hidden = key !== view;
    find("[data-desk-tasks]").hidden = view !== "reservations";
    find("[data-desk-waitlist]").hidden = view !== "reservations";
    if (focus) (sections[view].querySelector("h2[tabindex]") ?? find("h1")).focus();
    refresh().catch(error => {
      if (view !== section) return;
      focusReadyOrder = false;
      workspaceNotice.textContent = error.message;
    });
  };
}
