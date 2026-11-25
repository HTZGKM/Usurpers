const restaurantCsrf = document.querySelector('meta[name="restaurant-csrf"]').content;

async function restaurantRequest(path, fields, method = fields === undefined ? "GET" : "POST") {
  const form = fields === undefined ? undefined : new URLSearchParams({
    ...fields, csrf_token: restaurantCsrf,
  });
  const response = await fetch(path, {
    method,
    body: form,
    headers: { Accept: "application/json" },
    cache: "no-store",
    mode: "same-origin",
    credentials: "same-origin",
    redirect: "error",
  });
  const type = response.headers.get("content-type") ?? "";
  const data = type.includes("application/json") ? await response.json() : null;
  if (response.ok && data?.ok) return data;
  const messages = {
    TABLE_UNAVAILABLE: "That table was just reserved. Choose another table.",
    VISIT_UNFINISHED_ITEMS: "Serve all remaining dishes before releasing this table.",
    CAPACITY_INSUFFICIENT: "That table is too small for this party.",
    STATE_CONFLICT: "This record has changed. Refresh and try again.",
  };
  if (path.startsWith("/frontdesk/reservation-api/")) delete messages.TABLE_UNAVAILABLE;
  if (path.startsWith("/reservation-api/")) {
    messages.TABLE_UNAVAILABLE = "That table is unavailable at the selected arrival time. Choose another table.";
  }
  const fallback = {
    400: "Check the form fields and try again.",
    401: "Your session expired. Sign in again.",
    403: "Your account cannot perform this action.",
    404: "This record is no longer available.",
    409: "This action conflicts with the current restaurant state. Refresh and try again.",
  };
  const fieldError = data?.errors?.csrf_token
    ? "Your form has expired. Refresh the page and try again."
    : Object.values(data?.errors ?? {}).flat().find(message => typeof message === "string");
  const message = fieldError || data?.message;
  const error = new Error(messages[data?.error] ?? (
    message && !/\p{Script=Han}/u.test(message) ? message :
      fallback[response.status] ?? "The restaurant service could not complete this request."
  ));
  error.status = response.status;
  error.code = data?.error;
  throw error;
}

async function restaurantSeating() {
  const response = await fetch("/?fragment=seating", {
    cache: "no-store", mode: "same-origin", credentials: "same-origin", redirect: "error",
  });
  if (!response.ok) throw new Error("Could not load table service. Sign in again if your session has expired.");
  const document = new DOMParser().parseFromString(await response.text(), "text/html");
  const payload = document.getElementById("restaurant-seating");
  if (!payload) throw new Error("Table service data is unavailable.");
  return JSON.parse(payload.textContent);
}

function restaurantOrderFields(lines) {
  const fields = {};
  lines.forEach((line, index) => {
    fields[`items-${index}-dish_id`] = line.dishId;
    fields[`items-${index}-quantity`] = line.quantity;
    fields[`items-${index}-note`] = line.note;
  });
  return fields;
}

function restaurantQuery(path, fields) {
  return path + "?" + new URLSearchParams(fields);
}

function restaurantCanEditOrder(order) {
  return order.status === "active" && order.payment_status === "unpaid" &&
    order.items.every(item => ["waiting", "cancelled"].includes(item.status));
}

function restaurantOrderEditor(order, path, menuItems, onSaved) {
  const dialog = document.createElement("dialog");
  dialog.className = "restaurant-order-dialog";
  dialog.setAttribute("aria-label", "Edit order #" + order.order_id);
  dialog.innerHTML = '<h2>Edit order #' + order.order_id + '</h2>' +
    '<form><div class="restaurant-order-fields"></div>' +
    '<p role="alert"></p><div class="restaurant-order-actions">' +
    '<button type="button" class="secondary" data-append-line>Add dish</button>' +
    '<button type="button" class="secondary" data-close-order-editor>Discard</button>' +
    '<button type="submit" class="primary">Save changes</button></div></form>';
  const form = dialog.querySelector("form");
  const container = form.querySelector(".restaurant-order-fields");
  const feedback = form.querySelector("[role=alert]");
  const save = form.querySelector("[type=submit]");
  const allowed = new Map(menuItems.map(item => [item.dish_id, item.dish_name]));
  function appendLine(item = {}) {
    const row = document.createElement("fieldset");
    row.innerHTML = '<label>Dish<select name="dish" required></select></label>' +
      '<label>Quantity<input name="qty" type="number" min="1" max="99" required></label>' +
      '<label>Kitchen note<input name="note" maxlength="200"></label>' +
      '<button type="button" class="secondary" data-remove-order-line>Remove item</button>';
    const dish = row.querySelector("select");
    const choices = new Map(allowed);
    if (item.dish_id && !choices.has(item.dish_id)) choices.set(item.dish_id, item.dish_name + " (unavailable)");
    for (const [id, name] of choices) {
      dish.add(new Option(name, id, false, id === item.dish_id));
    }
    row.querySelector('[name="qty"]').value = item.quantity ?? 1;
    row.querySelector('[name="note"]').value = item.note ?? "";
    container.append(row);
    return dish;
  }
  order.items.filter(item => item.status === "waiting").forEach(appendLine);
  const add = form.querySelector("[data-append-line]");
  add.disabled = allowed.size === 0;
  add.onclick = () => appendLine().focus();
  form.querySelector("[data-close-order-editor]").onclick = () => dialog.close();
  container.addEventListener("click", event => {
    const remove = event.target.closest("[data-remove-order-line]");
    if (!remove) return;
    remove.closest("fieldset").remove();
    (container.querySelector("select") ?? add).focus();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (save.disabled) return;
    const lines = Array.from(container.querySelectorAll("fieldset"), row => ({
      dishId: row.querySelector("select").value,
      quantity: row.querySelector('[name="qty"]').value,
      note: row.querySelector('[name="note"]').value,
    }));
    if (!lines.length || lines.some(line => !allowed.has(Number(line.dishId)))) {
      feedback.textContent = "Keep at least one dish and remove or replace any unavailable dishes.";
      return;
    }
    save.disabled = true;
    feedback.textContent = "";
    try {
      await restaurantRequest(path, restaurantOrderFields(lines));
      dialog.close();
      await onSaved();
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      save.disabled = false;
    }
  });
  dialog.addEventListener("cancel", event => {
    if (save.disabled) event.preventDefault();
  });
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  document.body.append(dialog);
  dialog.showModal();
}
