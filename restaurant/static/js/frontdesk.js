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
  let filtersTimer;

  dateFilter.value = today();
  find("[data-desk-date]").textContent = today();
  const chosenBooking = () => bookings.find(row => row.booking_id === bookingId);
  const chosenVisit = () => visits.find(row => row.visit_id === visitId && row.status === "seated");
  const fieldValues = (form) => Object.fromEntries([...new FormData(form)].filter(([, value]) => value !== ""));
  const option = (value, label) => '<option value="' + value + '">' + esc(label) + '</option>';
  const deskButton = (label, attrs) => '<button type="button" class="desk-subtle" ' + attrs + '>' + label + '</button>';

  function setTableOptions(select, rows, selected) {
    select.innerHTML = rows.map(row => option(row.table_id, tableLabel(row.table_id) + " · " + row.capacity + " seats")).join("");
    if (rows.some(row => row.table_id === selected)) select.value = selected;
  }

  function renderReception() {
    const visible = bookings.filter(row => !phoneFilter.value.trim() ||
      row.phone_number.includes(phoneFilter.value.trim()));
    find("[data-desk-bookings]").innerHTML = visible.map(row =>
      '<li><button type="button" class="desk-booking" data-desk-booking="' + row.booking_id +
      '" aria-pressed="' + (row.booking_id === bookingId) + '"><strong>' + esc(row.contact_name) +
      '</strong><span>' + esc(row.phone_number) + '</span><span class="desk-booking-time">' +
      esc(row.time_slot) + ' · ' + esc(tableLabel(row.table_id) || "Unassigned") + ' · ' +
      esc(bookingLabels[row.status] ?? row.status) + '</span></button></li>'
    ).join("");
    find("[data-desk-empty]").hidden = visible.length > 0;
    find("[data-desk-booking-count]").textContent = visible.length + " reservations";
    find("[data-desk-occupied]").textContent = occupancy.filter(table => table.status === "occupied").length +
      " / " + occupancy.length + " occupied";
    for (const tile of workspace.querySelectorAll("[data-desk-table]")) {
      const id = tableIds[tile.dataset.deskTable];
      const row = occupancy.find(table => table.table_id === id);
      tile.dataset.tone = row?.status ?? "available";
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
      setTableOptions(checkIn.elements.table_id, available, row.table_id);
      checkIn.querySelector("[type=submit]").disabled = available.length === 0;
    }
  }

  function renderDraft() {
    find("[data-service-draft]").innerHTML = draft.map((line, index) =>
      '<li><span>' + line.quantity + ' × ' + esc(line.name) + (line.note ? ' · ' + esc(line.note) : '') +
      '</span>' + deskButton("Remove", 'data-draft-remove="' + index + '"') + '</li>').join("");
    find("[data-place-desk-order]").disabled = !draft.length;
  }

  function renderWaitlist() {
    const select = callForm.elements.table_id;
    setTableOptions(select, freeTables, Number(select.value));
    select.disabled = !freeTables.length;
    callForm.querySelector("[type=submit]").disabled = !freeTables.length || !queue.some(row => row.status === "waiting");
    find("[data-desk-waiting-empty]").hidden = queue.length > 0;
    find("[data-desk-waiting-list]").innerHTML = queue.map(row => {
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
    }).join("");
  }

  function orderCard(order) {
    const items = order.items.map(item => {
      const path = "/frontdesk/orders/" + order.order_id + "/items/" + item.order_item_id;
      return '<li><span>' + item.quantity + ' × ' + esc(item.dish_name) + ' · ' +
        esc({ waiting: "Waiting", cooking: "Cooking", ready: "Ready", served: "Served", cancelled: "Cancelled" }[item.status] ?? item.status) +
        (item.note ? '<small>' + esc(item.note) + '</small>' : '') + '</span>' +
        (item.status === "ready" ? deskButton("Mark served", 'data-desk-write="' + path + '/serve"') :
          item.status === "waiting" && order.payment_status === "unpaid"
            ? deskButton("Cancel item", 'data-desk-write="' + path + '/cancel"') : '') + '</li>';
    }).join("");
    return '<article class="desk-service-order" data-service-order="' + order.order_id + '"><h4>' +
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
    find("[data-service-feedback]").textContent = message;
    find("[data-close-desk-visit]").disabled = Boolean(message);
    find("[data-release-desk-table]").disabled = Boolean(message);
    if (message) find("[data-confirm-desk-close]").hidden = true;
  }

  async function refresh() {
    const current = ++revision;
    if (view === "reservations") {
      const filters = { date: dateFilter.value };
      if (slotFilter.value) filters.time_slot_id = slotFilter.value;
      const occupancySlot = chosenBooking()?.time_slot;
      const slot = slotFilter.value || Object.keys(slots).find(key => slots[key] === occupancySlot) || "2";
      const [list, floor, seating, waiting] = await Promise.all([
        restaurantRequest(restaurantQuery("/frontdesk/bookings", filters)),
        restaurantRequest(restaurantQuery("/frontdesk/tables", { date: filters.date, time_slot_id: slot })),
        restaurantSeating(),
        restaurantRequest("/frontdesk/waiting-queue"),
      ]);
      if (current !== revision) return;
      bookings = list.bookings;
      occupancy = floor.tables;
      visits = seating;
      queue = waiting.queue;
      freeTables = waiting.tables;
      renderReception();
      renderWaitlist();
    } else if (view === "service") {
      renderCloseControls(null);
      const [seating, waiting] = await Promise.all([restaurantSeating(), restaurantRequest("/frontdesk/waiting-queue")]);
      if (current !== revision) return;
      visits = seating;
      const unassigned = visits.filter(row => row.status === "waiting");
      find("[data-desk-unassigned]").innerHTML = unassigned.map(row =>
        '<form class="desk-check-in" data-assign-visit="' + row.visit_id + '"><span>' + esc(row.contact_name || "Walk-in") +
        '</span><label>Table <select name="table_id" required>' +
        waiting.tables.filter(table => table.capacity >= row.party_size).map(table => option(table.table_id, tableLabel(table.table_id))).join("") +
        '</select></label><button type="submit" class="desk-confirm">Assign table</button></form>'
      ).join("");
      const seated = visits.filter(row => row.status === "seated");
      find("[data-desk-service-picker]").innerHTML = seated.map(row => deskButton(
        esc(tableLabel(row.table_id)) + " · " + esc(row.contact_name || "Walk-in"),
        'data-live-visit="' + row.visit_id + '" aria-pressed="' + (visitId === row.visit_id) + '"'
      )).join("") || "<p>No guests are seated.</p>";
      const visit = chosenVisit();
      find("[data-desk-service]").hidden = !visit;
      if (!visit) return;
      find("[data-service-visit]").textContent = "Table " + tableLabel(visit.table_id);
      const [menuData, orderData] = await Promise.all([
        restaurantRequest("/frontdesk/menu"),
        restaurantRequest(restaurantQuery("/frontdesk/orders", { table_id: visit.table_id })),
      ]);
      const orders = await Promise.all(orderData.orders.filter(row => row.visit_id === visit.visit_id)
        .map(row => restaurantRequest("/frontdesk/orders/" + row.order_id)));
      if (current !== revision) return;
      serviceMenu = menuData.items;
      serviceOrders = orders.map(result => result.order);
      const dishField = serviceForm.elements.dish;
      const selected = dishField.value;
      dishField.innerHTML = menuData.items.map(row => option(row.dish_id, row.dish_name + " · ¥" + row.price)).join("");
      if (menuData.items.some(row => row.dish_id === Number(selected))) dishField.value = selected;
      serviceForm.querySelector("[type=submit]").disabled = !menuData.items.length;
      renderDraft();
      find("[data-service-orders]").innerHTML = serviceOrders.map(orderCard).join("") || "<p>No orders for this visit.</p>";
      renderCloseControls(serviceOrders);
    } else {
      const { orders } = await restaurantRequest("/frontdesk/orders");
      if (current === revision) renderBilling(orders);
    }
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
      visitId = visit.visit_id;
      draft = [];
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
      visitId = visit.visit_id;
      draft = [];
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
    if (data.deskBooking) {
      bookingId = Number(data.deskBooking);
      tableId = chosenBooking().table_id;
      renderReception();
      return update(async () => "");
    }
    if (data.deskTable) {
      tableId = tableIds[data.deskTable];
      feedback.textContent = "Table " + data.deskTable;
      return renderReception();
    }
    if (data.deskOpen === "service") {
      visitId = visits.find(row => row.table_id === tableId && row.status === "seated")?.visit_id;
      draft = [];
      return navigate("service");
    }
    if (data.deskOpen) return openDialog(data.deskOpen);
    if (data.liveVisit) {
      const next = Number(data.liveVisit);
      if (visitId !== next) draft = [];
      visitId = next;
      find("[data-confirm-desk-close]").hidden = true;
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
      await restaurantRequest(data.deskWrite, {});
      return "Order updated.";
    });
    const closeConfirmation = find("[data-confirm-desk-close]");
    if (button.matches("[data-close-desk-visit],[data-keep-desk-visit]")) {
      closeConfirmation.hidden = button.matches("[data-keep-desk-visit]");
    }
    if (button.matches("[data-release-desk-table]")) return update(async () => {
      const { visit } = await restaurantRequest("/frontdesk/visits/" + visitId + "/close", {});
      closeConfirmation.hidden = true;
      visitId = undefined;
      draft = [];
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

  return (section, focus) => {
    view = section;
    const sections = { reservations: find("[data-desk-reception]"), service: find("[data-desk-service-view]"),
      billing: find("[data-desk-billing]") };
    for (const [key, panel] of Object.entries(sections)) panel.hidden = key !== view;
    find("[data-desk-waitlist]").hidden = view !== "reservations";
    if (focus) (sections[view].querySelector("h2[tabindex]") ?? find("h1")).focus();
    refresh().catch(error => { workspaceNotice.textContent = error.message; });
  };
}
