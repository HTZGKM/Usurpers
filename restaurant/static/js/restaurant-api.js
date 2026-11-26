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

const pendingRestaurantSubmissions = new Map();

async function restaurantSubmitOnce(path, fields) {
  const actor = JSON.parse(document.querySelector("#guest-data").textContent).account;
  const scope = "double-portion-submit:" + actor.role + ":" + actor.username + ":" + path + ":" + (fields.visit_id ?? "");
  const body = Object.fromEntries(Object.entries(fields).sort(([left], [right]) => left.localeCompare(right)));
  let pending = pendingRestaurantSubmissions.get(scope);
  try { pending ??= JSON.parse(sessionStorage.getItem(scope)); } catch {}
  const recoveredPrevious = Boolean(pending && JSON.stringify(pending.body) !== JSON.stringify(body));
  if (recoveredPrevious && !window.confirm("A previous submission is unconfirmed. Retry its original details before sending this draft?")) {
    throw new Error("The previous submission is still unconfirmed. Your current draft is available to review.");
  }
  pending ??= { body, key: crypto.randomUUID() };
  pendingRestaurantSubmissions.set(scope, pending);
  try { sessionStorage.setItem(scope, JSON.stringify(pending)); } catch {}
  function clear() {
    pendingRestaurantSubmissions.delete(scope);
    try { sessionStorage.removeItem(scope); } catch {}
  }
  try {
    const result = await restaurantRequest(path, { ...pending.body, idempotency_key: pending.key });
    clear();
    return { ...result, recoveredPrevious };
  } catch (error) {
    if ([400, 404, 409, 422].includes(error.status)) clear();
    throw error;
  }
}

function restaurantOrderFields(lines) {
  const fields = {};
  lines.forEach((line, index) => {
    fields[`items-${index}-dish_id`] = line.dishId;
    fields[`items-${index}-quantity`] = line.quantity;
    fields[`items-${index}-note`] = line.note;
    if (Number.isFinite(line.unitPrice)) fields[`items-${index}-quoted_unit_cents`] = Math.round(line.unitPrice * 100);
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

function restaurantCanPayOrder(order) {
  return order.status !== "cancelled" && order.payment_status === "unpaid" &&
    (order.order_type !== "preorder" || Boolean(order.visit_id));
}

function restaurantPreorderWaiting(order, item) {
  if (order.order_type !== "preorder" || item.status !== "waiting" || item.kitchen_status) return "";
  if (!order.visit_id) return "Awaiting seating";
  if (!item.estimated_ready_at) return "Scheduled for kitchen";
  const timestamp = item.estimated_ready_at.replace(" ", "T");
  const time = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(timestamp) ? timestamp : timestamp + "Z");
  return Number.isFinite(time.getTime()) ? "Scheduled · from " + time.toLocaleTimeString("en-GB", {
    timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit",
  }) : "Scheduled for kitchen";
}

function restaurantCancelledItems(items) {
  const cancelled = items.filter(item => item.status === "cancelled");
  if (!cancelled.length) return "";
  return '<details class="restaurant-cancelled-items"><summary>Removed or cancelled items (' + cancelled.length +
    ')</summary><ul>' + cancelled.map(item => '<li>' + item.quantity + ' × ' + esc(item.dish_name) + '</li>').join("") +
    '</ul></details>';
}

function restaurantOrderEditor(order, path, menuItems, onSaved) {
  const dialog = document.createElement("dialog");
  dialog.className = "restaurant-order-dialog";
  dialog.setAttribute("aria-label", "Edit order #" + order.order_id);
  dialog.innerHTML = '<h2>Edit order #' + order.order_id + '</h2>' +
    '<form><div class="restaurant-order-fields"></div>' +
    '<p role="alert"></p><p data-latest-order></p><div class="restaurant-order-actions">' +
    '<button type="button" class="secondary" data-refresh-order-editor hidden>Load latest order</button>' +
    '<button type="button" class="secondary" data-append-line>Add dish</button>' +
    '<button type="button" class="secondary" data-close-order-editor>Discard</button>' +
    '<button type="submit" class="primary">Save changes</button></div></form>';
  const form = dialog.querySelector("form");
  const container = form.querySelector(".restaurant-order-fields");
  const feedback = form.querySelector("[role=alert]");
  const save = form.querySelector("[type=submit]");
  const reload = form.querySelector("[data-refresh-order-editor]");
  let expectedVersion = order.version;
  let needsReload = false;
  reload.onclick = async () => {
    reload.disabled = true;
    try {
      const { order: current } = await restaurantRequest(path.replace(/\/edit$/, ""));
      form.querySelector("[data-latest-order]").textContent = "Latest order · " + current.items.filter(item => item.status !== "cancelled")
        .map(item => item.quantity + " × " + item.dish_name + (item.note ? " (" + item.note + ")" : "")).join(", ");
      expectedVersion = current.version;
      needsReload = !restaurantCanEditOrder(current);
      feedback.textContent = needsReload ? "This order can no longer be edited." : "Review the latest order before applying your draft.";
      reload.hidden = true;
      save.disabled = needsReload;
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      reload.disabled = false;
    }
  };
  const allowed = new Map(menuItems.map(item => [item.dish_id, item.dish_name]));
  const prices = new Map(menuItems.map(item => [item.dish_id, Number(item.price)]));
  const choiceLabel = (id, name) => Number.isFinite(prices.get(id)) ? name + " · ¥" + prices.get(id).toFixed(2) : name;
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
      dish.add(new Option(choiceLabel(id, name), id, false, id === item.dish_id));
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
      unitPrice: prices.get(Number(row.querySelector("select").value)),
    }));
    if (!lines.length || lines.some(line => !allowed.has(Number(line.dishId)))) {
      feedback.textContent = "Keep at least one dish and remove or replace any unavailable dishes.";
      return;
    }
    save.disabled = true;
    feedback.textContent = "";
    try {
      await restaurantRequest(path, { ...restaurantOrderFields(lines), expected_version: expectedVersion });
      dialog.close();
      await onSaved();
    } catch (error) {
      feedback.textContent = error.message;
      if (error.code === "ORDER_CHANGED") {
        needsReload = true;
        reload.hidden = false;
        reload.focus();
      } else if (error.code === "PRICE_CHANGED") {
        try {
          const { items } = await restaurantRequest(path.startsWith("/frontdesk/") ? "/frontdesk/menu" : "/menu");
          for (const item of items) prices.set(item.dish_id, Number(item.price));
          for (const option of container.querySelectorAll("option")) {
            const id = Number(option.value);
            if (allowed.has(id)) option.textContent = choiceLabel(id, allowed.get(id));
          }
        } catch {
          feedback.textContent += " Reload the menu to check the current price.";
        }
      }
    } finally {
      save.disabled = needsReload;
    }
  });
  dialog.addEventListener("cancel", event => {
    if (save.disabled) event.preventDefault();
  });
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  document.body.append(dialog);
  dialog.showModal();
}
