function mountDeskService(section, demo, closeVisit) {
  const form = section.querySelector("[data-service-form]");
  const draftView = section.querySelector("[data-service-draft]");
  const orderView = section.querySelector("[data-service-orders]");
  const place = section.querySelector("[data-place-desk-order]");
  const close = section.querySelector("[data-close-desk-visit]");
  const confirm = section.querySelector("[data-confirm-desk-close]");
  const feedback = section.querySelector("[data-service-feedback]");
  const drafts = new Map();
  let current;

  const orders = () => demo.orders.filter((order) => order.visit === current.key);
  const unpaid = () => orders().some((order) => !order.paidAt && staffOrderStatus(order) !== "Cancelled");
  const available = () => demo.dishes.filter((dish) => !dish.sold && !dish.archived);

  function showDraft() {
    const draft = drafts.get(current.key) ?? [];
    draftView.innerHTML = draft.map((item, index) => '<li>' + itemMarkup(item) +
      '<button type="button" class="desk-subtle" data-remove-desk-item="' + index + '">Remove</button></li>').join("");
    place.textContent = draft.length ? "Place order · " + staffPrice(staffOrderTotal({ items: draft })) : "Place order";
    place.disabled = draft.length === 0;
  }

  function itemMarkup(item) {
    return '<span><strong>' + item.quantity + ' × ' + esc(item.name) + '</strong>' +
      (item.note ? '<small>' + esc(item.note) + '</small>' : '') + '</span>';
  }

  function showOrders() {
    orderView.innerHTML = orders().map((order) => {
      const status = staffOrderStatus(order);
      return '<article class="desk-service-order" data-desk-order="' + order.id + '">' +
        '<div class="desk-panel-heading"><strong>Order #' + order.id + '</strong><span>' + status + ' · ' +
        (order.paidAt ? 'Paid' : status === 'Cancelled' ? 'No payment required' : 'Unpaid') + '</span></div>' +
        '<ul class="desk-service-list">' + order.items.map((item) => {
          const action = item.status === "Ready" ? "Mark served" : item.status === "Queued" && !order.paidAt ? "Cancel item" : "";
          return '<li>' + itemMarkup(item) + '<span class="desk-item-status">' + item.status + '</span>' +
            (action ? '<button type="button" class="desk-subtle" data-desk-item="' + item.id +
              '" aria-label="' + action + ': ' + esc(item.name) + '">' + action + '</button>' : '') + '</li>';
        }).join("") + '</ul><div class="desk-service-total"><strong>' + staffPrice(staffOrderTotal(order)) + '</strong>' +
        (order.paidAt || status === "Cancelled" ? '' : '<button type="button" class="desk-subtle" data-pay-desk-order>Record payment</button>') +
        '</div></article>';
    }).join("") || '<p class="desk-floor-feedback">No orders for this visit.</p>';
    close.disabled = unpaid();
    if (close.disabled) close.title = "Record payment for open orders first.";
    else close.removeAttribute("title");
  }

  function render(visit) {
    current = visit;
    section.hidden = !visit;
    confirm.hidden = true;
    feedback.textContent = "";
    if (!visit) return;
    section.querySelector("h2").textContent = "Table " + visit.table + " service";
    section.querySelector("[data-service-visit]").textContent = visit.label;
    form.elements.dish.replaceChildren(new Option("Select a dish", ""), ...available().map((dish) =>
      new Option(dish.name + " · " + staffPrice(dish.price), dish.key),
    ));
    form.reset();
    showDraft();
    showOrders();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!current) return;
    const dish = available().find((entry) => entry.key === form.elements.dish.value);
    if (!dish) return;
    const draft = drafts.get(current.key) ?? [];
    draft.push({ key: dish.key, name: dish.name, price: dish.price, quantity: form.elements.quantity.valueAsNumber,
      note: form.elements.note.value.trim(), status: "Queued" });
    drafts.set(current.key, draft);
    feedback.textContent = "";
    form.reset();
    showDraft();
    form.elements.dish.focus();
  });

  section.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!current || !button || button.disabled) return;
    const order = orders().find((entry) => entry.id === Number(button.closest("[data-desk-order]")?.dataset.deskOrder));
    if (button.matches("[data-remove-desk-item]")) {
      drafts.get(current.key).splice(Number(button.dataset.removeDeskItem), 1);
      showDraft();
      form.elements.dish.focus();
    } else if (button === place) {
      const draft = drafts.get(current.key) ?? [];
      if (!draft.length) return;
      const id = Math.max(1044, ...demo.orders.map((entry) => entry.id)) + 1;
      demo.orders.push({ id, visit: current.key, table: current.table, date: current.date,
        time: new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }), paidAt: null,
        items: draft.map((item, index) => ({ ...item, id: index + 1 })),
      });
      drafts.delete(current.key);
      saveStaffDemo(demo);
      showDraft();
      showOrders();
      feedback.textContent = "Order #" + id + " sent to the demo kitchen queue.";
    } else if (order && button.matches("[data-desk-item]")) {
      const item = order.items.find((entry) => entry.id === Number(button.dataset.deskItem));
      if (item?.status === "Ready") item.status = "Served";
      else if (item?.status === "Queued" && !order.paidAt) item.status = "Cancelled";
      else return;
      saveStaffDemo(demo);
      showOrders();
      feedback.textContent = item.name + " · " + item.status;
    } else if (order && button.matches("[data-pay-desk-order]")) {
      if (order.paidAt || staffOrderStatus(order) === "Cancelled") return;
      order.paidAt = new Date().toISOString();
      saveStaffDemo(demo);
      showOrders();
      feedback.textContent = "Payment recorded for order #" + order.id + ".";
    } else if (button === close) {
      confirm.hidden = false;
      confirm.querySelector("button").focus();
    } else if (button.matches("[data-keep-desk-visit]")) {
      confirm.hidden = true;
      close.focus();
    } else if (button.matches("[data-release-desk-table]") && !unpaid()) {
      drafts.delete(current.key);
      closeVisit(current);
    }
  });

  return render;
}
