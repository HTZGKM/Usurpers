function installBookingCalendar(form, calendar) {
  if (typeof calendar.showModal !== "function") return;

  const input = form.querySelector("#date");
  const label = form.querySelector("#booking-date-label");
  const toggle = form.querySelector(".booking-date-toggle");
  const value = toggle.querySelector("#booking-date-value");
  const days = calendar.querySelector("[data-calendar-days]");
  const monthLabel = calendar.querySelector("[data-calendar-label]");
  const previous = calendar.querySelector('[data-calendar-month="-1"]');
  const dateOptions = { timeZone: "UTC" };
  const dateFormat = new Intl.DateTimeFormat("en-GB", {
    ...dateOptions, day: "numeric", month: "short", year: "numeric",
  });
  const fullDateFormat = new Intl.DateTimeFormat("en-GB", {
    ...dateOptions, dateStyle: "full",
  });
  const monthFormat = new Intl.DateTimeFormat("en-GB", {
    ...dateOptions, month: "long", year: "numeric",
  });
  const dayLength = 86400000;
  const minimum = Date.parse(input.min);
  const monthStart = (date, offset = 0) => {
    const day = new Date(date);
    return Date.UTC(day.getUTCFullYear(), day.getUTCMonth() + offset, 1);
  };
  let activeDate;

  function render(focusDay = false) {
    const first = monthStart(activeDate);
    const end = monthStart(activeDate, 1);
    const offset = (new Date(first).getUTCDay() + 6) % 7;
    monthLabel.textContent = monthFormat.format(first);
    previous.disabled = first === monthStart(minimum);
    days.replaceChildren();
    for (let index = 0; index < offset; index++) {
      days.append(document.createElement("span"));
    }
    for (let date = first; date < end; date += dayLength) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "booking-day";
      button.dataset.calendarDate = date;
      button.textContent = new Date(date).getUTCDate();
      button.setAttribute("aria-label", fullDateFormat.format(date));
      button.setAttribute("aria-pressed", date === input.valueAsNumber);
      if (date === minimum) button.setAttribute("aria-current", "date");
      button.disabled = date < minimum;
      button.tabIndex = date === activeDate ? 0 : -1;
      days.append(button);
    }
    if (focusDay) days.querySelector('[tabindex="0"]').focus();
  }

  function selectDate(date) {
    input.valueAsNumber = date;
    value.textContent = dateFormat.format(date);
    input.dispatchEvent(new Event("change", { bubbles: true }));
    calendar.close();
  }

  toggle.addEventListener("click", () => {
    activeDate = input.valueAsNumber;
    render();
    calendar.showModal();
    days.querySelector('[tabindex="0"]').focus();
  });
  calendar.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.hasAttribute("data-calendar-close")) calendar.close();
    else if (button.hasAttribute("data-calendar-today")) selectDate(minimum);
    else if (button.dataset.calendarDate) selectDate(Number(button.dataset.calendarDate));
    else if (button.dataset.calendarMonth) {
      activeDate = Math.max(minimum, monthStart(activeDate, Number(button.dataset.calendarMonth)));
      render(button === previous && activeDate === minimum);
    }
  });
  days.addEventListener("keydown", (event) => {
    const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    if (offset === undefined || !event.target.matches(".booking-day")) return;
    event.preventDefault();
    activeDate = Math.max(minimum, Number(event.target.dataset.calendarDate) + offset * dayLength);
    render(true);
  });
  calendar.addEventListener("close", () => toggle.focus());

  value.textContent = dateFormat.format(input.valueAsNumber);
  label.htmlFor = "";
  input.hidden = true;
  toggle.hidden = false;
}
