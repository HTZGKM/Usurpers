function mountFrontdeskWorkspace(workspace, username, tables, slots, date, demo) {
  if (!demo.receptionMigrated) {
    const previous = readStaffPreview("double-portion-frontdesk-preview-v2." + username);
    const legacyArrivals = readStaffPreview("double-portion-frontdesk-preview-v1." + username + "." + date);
    if (previous) demo.reception = previous;
    else if (legacyArrivals) demo.reception.arrivals = legacyArrivals;
    demo.receptionMigrated = true;
    saveStaffDemo(demo);
  }
  const { bookings, arrivals, walkIns } = demo.reception;
  const save = () => saveStaffDemo(demo);

  const dates = workspace.querySelector("[data-desk-date]");
  dates.dateTime = date;
  dates.textContent = new Date(date + "T12:00:00").toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "long", year: "numeric",
  });
  const viewDate = workspace.querySelector("[data-desk-view-date]");
  viewDate.value = date;
  const slot = workspace.querySelector("[data-desk-slot]");
  const search = workspace.querySelector("[data-desk-search]");
  const list = workspace.querySelector("[data-desk-bookings]");
  const form = workspace.querySelector("[data-desk-check-in]");
  const actualTable = form.elements.table_id;
  const feedback = workspace.querySelector("[data-desk-arrival-feedback]");
  const floorFeedback = workspace.querySelector("[data-desk-floor-feedback]");
  const walkInButton = workspace.querySelector('[data-desk-open="walk-in"]');
  const serviceButton = workspace.querySelector('[data-desk-open="service"]');
  const serviceSection = workspace.querySelector("[data-desk-service]");
  const renderService = mountDeskService(serviceSection, demo, (visit) => {
    visit.record.closedAt = new Date().toISOString();
    save();
    select(null, visit.table);
    announce(floorFeedback, "Visit closed. Table " + visit.table + " is available for its next booking.");
  });
  const bookingActions = workspace.querySelector("[data-desk-booking-actions]");
  const capacities = new Map(tables.map(([id, capacity]) => [id, capacity]));

  const dialog = workspace.querySelector(".desk-dialog");
  const editor = dialog.querySelector("[data-desk-editor]");
  const walkInForm = dialog.querySelector("[data-desk-walk-in]");
  const cancellation = dialog.querySelector("[data-desk-cancellation]");
  const context = dialog.querySelector("[data-desk-dialog-copy]");
  const editorError = dialog.querySelector("[data-desk-editor-error]");
  const walkInError = dialog.querySelector("[data-desk-walk-error]");
  editor.elements.booking_date.min = date;
  editor.elements.party_size.max = Math.max(...capacities.values());
  let mode = "";
  let selected = bookings.find((booking) => booking.date === date && !booking.cancelled);
  let selectedTable = "";

  const viewedDate = () => viewDate.value || date;
  const editable = (booking) => booking && booking.date >= date && !booking.cancelled && !arrivals[booking.id];
  const guestCount = (guests) => guests + (guests === 1 ? " guest" : " guests");

  function occupancy(table) {
    return staffActiveVisit(demo.reception, table, date);
  }

  function locatedAt(table) {
    return staffTableState(demo.reception, table, viewedDate(), slot.value, date);
  }

  function canSeat(booking, table) {
    return capacities.get(table) >= booking.guests &&
      (booking.date !== date || !occupancy(table)) &&
      !bookings.some((other) => other.id !== booking.id && !other.cancelled && !other.closedAt &&
        other.date === booking.date && other.time === booking.time &&
        (arrivals[other.id] ?? other.table) === table);
  }

  function renderFloor() {
    let occupied = 0;
    for (const button of workspace.querySelectorAll("[data-desk-table]")) {
      const table = button.dataset.deskTable;
      const { status } = locatedAt(table);
      occupied += Number(status === "Occupied");
      button.dataset.tone = status.toLowerCase();
      button.setAttribute("aria-label", "Table " + table + ", " + capacities.get(table) + " seats, " + status);
      button.setAttribute("aria-pressed", String(table === selectedTable));
    }
    workspace.querySelector("[data-desk-occupied]").textContent = occupied + " of " + tables.length + " occupied";
    const location = locatedAt(selectedTable);
    const label = selectedTable
      ? "Table " + selectedTable + " · " + capacities.get(selectedTable) + " seats · " + location.status
      : "Select a table to see its status.";
    floorFeedback.textContent = label + (location.walkIn ? " · Walk-in, " + guestCount(location.walkIn.guests) : "");
    walkInButton.hidden = viewedDate() !== date || !selectedTable || location.status !== "Available";
    serviceButton.hidden = !selectedTable || location.status !== "Occupied";
  }

  function matchesFilters(booking) {
    const digits = search.value.replace(/\D/g, "");
    return booking.date === viewedDate() && (!slot.value || booking.time === slot.value) &&
      booking.phone.replace(/\D/g, "").includes(digits);
  }

  function renderBookings() {
    const visible = bookings.filter(matchesFilters).sort((a, b) => slots.indexOf(a.time) - slots.indexOf(b.time));
    list.innerHTML = visible.map((booking) => {
      const table = arrivals[booking.id] ?? booking.table;
      const checkedIn = Boolean(arrivals[booking.id]);
      const tone = booking.cancelled || booking.closedAt ? "cancelled" : checkedIn ? "occupied" : "reserved";
      const status = booking.cancelled ? "Cancelled" : booking.closedAt ? "Completed" : checkedIn ? "Checked in" : "Expected";
      return '<li><button class="desk-booking" type="button" data-desk-booking="' + booking.id +
        '" aria-pressed="' + (selected === booking) + '">' +
        '<span class="desk-booking-time">' + esc(booking.time) + '</span>' +
        '<span class="desk-guest"><strong>' + esc(booking.name) + '</strong><small>' +
        guestCount(booking.guests) + ' · ' + (table ? 'Table ' + esc(table) : 'No table assigned') + '</small></span>' +
        '<span class="desk-chip" data-tone="' + tone + '">' + status + '</span></button></li>';
    }).join("");
    workspace.querySelector("[data-desk-empty]").hidden = visible.length !== 0;
    workspace.querySelector("[data-desk-booking-count]").textContent = visible.length + (visible.length === 1 ? " booking" : " bookings");
    workspace.querySelector("#desk-bookings-title").textContent = viewedDate() === date ? "Today's reservations" : "Reservations";
  }

  function renderArrival() {
    const copy = workspace.querySelector("[data-desk-arrival-copy]");
    const checkedIn = selected && arrivals[selected.id];
    bookingActions.hidden = !editable(selected);
    form.hidden = !editable(selected) || selected.date !== date;
    workspace.querySelector("#desk-arrival-title").textContent = viewedDate() === date ? "Check in" : "Booking details";
    if (!selected) {
      copy.textContent = viewedDate() === date ? "Select a reservation to check in a guest." : "Select a reservation to view its details.";
      return;
    }
    if (checkedIn || selected.cancelled) {
      const status = selected.closedAt ? " · Visit completed" : checkedIn ? " · Checked in at table " + checkedIn : " · Cancelled";
      copy.textContent = selected.name + status;
      return;
    }
    copy.textContent = [selected.name, selected.phone, guestCount(selected.guests)].join(" · ");
    if (form.hidden) return;
    actualTable.replaceChildren(
      new Option("Select a table", ""),
      ...tables.filter(([id]) => canSeat(selected, id))
        .map(([id, capacity]) => new Option("Table " + id + " · " + capacity + " seats", id)),
    );
    actualTable.value = selected.table && canSeat(selected, selected.table) ? selected.table : "";
    form.querySelector("button[type=submit]").disabled = !actualTable.value;
  }

  function select(booking, table = "") {
    selected = booking;
    selectedTable = table || (booking && !booking.cancelled && !booking.closedAt ? arrivals[booking.id] ?? booking.table : "");
    feedback.hidden = true;
    renderService(null);
    renderFloor();
    renderBookings();
    renderArrival();
  }

  function applyFilters() {
    if (selected && !matchesFilters(selected)) select(null);
    else {
      renderFloor();
      renderBookings();
    }
  }
  slot.addEventListener("change", applyFilters);
  search.addEventListener("input", applyFilters);
  viewDate.addEventListener("change", () => {
    select(bookings.find((booking) => !booking.cancelled && matchesFilters(booking)));
  });
  actualTable.addEventListener("change", () => {
    selectedTable = actualTable.value;
    form.querySelector("button[type=submit]").disabled = !selectedTable;
    renderFloor();
  });

  function announce(element, message) {
    element.textContent = message;
    element.hidden = false;
    element.tabIndex = -1;
    element.focus();
  }

  function openDialog(action) {
    if ((action === "edit" || action === "cancel") && !editable(selected)) return;
    if (action === "walk-in" && walkInButton.hidden) return;
    mode = action;
    const title = {
      new: "New booking", edit: "Edit booking", cancel: "Cancel booking", "walk-in": "Seat walk-in",
    }[action];
    dialog.querySelector("h2").textContent = title;
    editor.hidden = action !== "new" && action !== "edit";
    walkInForm.hidden = action !== "walk-in";
    cancellation.hidden = action !== "cancel";
    context.hidden = action === "new";
    editorError.hidden = walkInError.hidden = true;
    if (!editor.hidden) {
      editor.reset();
      const existing = action === "edit" ? selected : null;
      const contact = editor.querySelector("[data-desk-contact]");
      contact.hidden = contact.disabled = Boolean(existing);
      editor.elements.booking_date.value = existing?.date ?? (viewedDate() >= date ? viewedDate() : date);
      editor.elements.time_slot.value = existing?.time ?? (slot.value || slots[0]);
      editor.elements.party_size.value = existing?.guests ?? 2;
      editor.querySelector("[data-desk-editor-submit]").textContent = existing ? "Save changes" : "Create booking";
      if (existing) context.textContent = existing.name + " · " + existing.phone;
    } else if (action === "walk-in") {
      walkInForm.reset();
      walkInForm.elements.party_size.max = capacities.get(selectedTable);
      walkInForm.elements.party_size.value = Math.min(2, capacities.get(selectedTable));
      context.textContent = "Table " + selectedTable + " · " + capacities.get(selectedTable) + " seats";
    } else {
      context.textContent = "Cancel the reservation for " + selected.name + " at " + selected.time + "?";
    }
    dialog.showModal();
    if (action === "new") editor.elements.contact_name.focus();
    if (action === "edit") editor.elements.booking_date.focus();
    if (action === "walk-in") walkInForm.elements.party_size.focus();
  }

  function openService() {
    if (serviceButton.hidden) return;
    const { booking, walkIn } = locatedAt(selectedTable);
    const record = booking ?? walkIn;
    if (!record) return;
    const key = booking ? "booking-" + booking.date + "-" + booking.id : "walk-in-" + walkIns.indexOf(walkIn);
    renderService({ key, date, table: selectedTable, record,
      label: (booking?.name ?? "Walk-in") + " · " + guestCount(record.guests),
    });
    serviceSection.querySelector("h2").focus();
  }

  workspace.addEventListener("click", (event) => {
    const table = event.target.closest("[data-desk-table]");
    const booking = event.target.closest("[data-desk-booking]");
    const action = event.target.closest("[data-desk-open]");
    if (table) {
      const tableId = table.dataset.deskTable;
      select(locatedAt(tableId).booking, tableId);
    } else if (booking) {
      const id = booking.dataset.deskBooking;
      select(bookings.find((entry) => entry.id === Number(id)));
      list.querySelector('[data-desk-booking="' + id + '"]')?.focus({ preventScroll: true });
    } else if (action?.dataset.deskOpen === "service") openService();
    else if (action) openDialog(action.dataset.deskOpen);
    else if (event.target.closest("[data-desk-close]")) dialog.close();
  });

  function showBooking(booking, message) {
    save();
    dialog.close();
    viewDate.value = booking.date;
    if (slot.value !== booking.time) slot.value = "";
    if (!matchesFilters(booking)) search.value = "";
    select(booking);
    announce(feedback, message);
  }

  editor.addEventListener("input", () => { editorError.hidden = true; });

  editor.addEventListener("submit", (event) => {
    event.preventDefault();
    const original = mode === "edit" ? selected : null;
    if (mode === "edit" && !editable(original)) return;
    const fields = editor.elements;
    const draft = {
      id: original?.id ?? Math.max(...bookings.map((booking) => booking.id), 300) + 1,
      name: original?.name ?? fields.contact_name.value.trim(),
      phone: original?.phone ?? fields.phone_number.value.trim(),
      date: fields.booking_date.value,
      time: fields.time_slot.value,
      guests: fields.party_size.valueAsNumber,
    };
    if (!original && (!draft.name || !/^\+?\d+$/.test(draft.phone))) {
      announce(editorError, "Enter a name and a phone number with digits and an optional leading +.");
      return;
    }
    const bestFit = tables.filter(([id]) => canSeat(draft, id)).sort((a, b) => a[1] - b[1]);
    draft.table = original?.table && canSeat(draft, original.table) ? original.table : bestFit[0]?.[0];
    if (!draft.table) {
      announce(editorError, "No table fits this party at the selected date and time.");
      return;
    }
    if (original) Object.assign(original, draft);
    else bookings.push(draft);
    showBooking(original ?? draft, (original ? "Booking updated for " : "Booking created for ") + draft.name + ".");
  });

  cancellation.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!editable(selected)) return;
    selected.cancelled = true;
    showBooking(selected, "Booking cancelled for " + selected.name + ".");
  });

  walkInForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const table = selectedTable;
    const guests = walkInForm.elements.party_size.valueAsNumber;
    if (walkInButton.hidden || locatedAt(table).status !== "Available" || guests > capacities.get(table)) {
      announce(walkInError, "Select an available table with enough seats.");
      return;
    }
    walkIns.push({ table, guests, date });
    save();
    dialog.close();
    select(null, table);
    announce(floorFeedback, "Walk-in seated at table " + table + " · " + guestCount(guests) + ".");
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const table = actualTable.value;
    if (!editable(selected) || selected.date !== date || !canSeat(selected, table)) return;
    arrivals[selected.id] = table;
    save();
    select(selected, table);
    announce(feedback, "Arrival confirmed for " + selected.name + ". Table " + table + " is now occupied.");
  });

  select(selected);
}
