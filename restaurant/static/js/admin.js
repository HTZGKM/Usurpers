function mountAdminWorkspace(root, layout, catalog, navigate) {
  const main = root.querySelector('[data-workspace-view]');
  const userMenu = root.querySelector('.dp-user');
  const userButton = userMenu.querySelector('.dp-user-button');
  const userProfile = userMenu.querySelector('.dp-user-profile');
  const confirmation = root.querySelector('.dp-confirmation');
  const deactivation = root.querySelector('.dp-deactivation');
  const feedback = root.querySelector('[data-admin-feedback]');
  const csrf = root.querySelector('[name="csrf_token"]').value;
  const queueArt = Object.fromEntries(['burger','pizza','tea','water','fries','plate'].map(key =>
    [key, root.dataset.assetRoot + key + (key === 'plate' ? '.svg' : '.png')]));

  let serviceDate = '';
  let serviceTime = '';
  let floor = [];
  let reservations = [];
  let occupancy = [];
  let orders = [];
  let weekDays = [];
  let weekOrders = [];
  let kitchenOrders = [];
  let ledgerOrders = [];
  let orderDays = new Set();
  let accounts = [];
  let dishes = [];
  let loaded = false;
  let loading = null;
  let refreshedAt = 0;
  let ledgerRequest = 0;
  let ledgerDate = null;
  let ledgerLoading = false;
  let ledgerError = '';
  let pendingAction = null;

  const orderMonthLabel = new Intl.DateTimeFormat('en-GB', { month:'long', year:'numeric', timeZone:'UTC' });
  const orderDateLabel = new Intl.DateTimeFormat('en-GB', { day:'numeric', month:'short', year:'numeric', timeZone:'UTC' });
  const titles = { overview:'Overview', orders:'Orders', queue:'Kitchen queue', floor:'Tables',
    timeline:'Tables', calendar:'Tables', accounts:'Accounts', dishes:'Dishes' };
  const tones = { 'In queue':'amber', Queued:'amber', Cooking:'amber', Unpaid:'amber', Reserved:'amber',
    Ready:'sage', Paid:'sage', Seated:'sage', Active:'sage', Cancelled:'rose', Unavailable:'rose' };
  const state = { view:'overview', date:'', calendarMonth:'', table:'', booking:'', order:'', orderDate:'',
    orderStatus:'', payment:'', orderLimit:100, role:'', account:'', accountEditing:false, category:'', dishStatus:'', dish:'', roseLimit:12,
    salesMetric:{ today:'revenue', week:'orders' } };
  const es = (value) => String(value).replace(/[&<>"']/g, char =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[char]);
  const tone = (status) => tones[status] || 'neutral';
  const dot = (color) => '<i aria-hidden="true" class="dp-dot" data-tone="' + color + '"></i>';
  const tag = (label) => '<span class="dp-tag" data-tone="' + tone(label) + '">' + es(label) + '</span>';
  const formatNumber = new Intl.NumberFormat('en', {maximumFractionDigits:2});
  const money = (amount) => '<span class="dp-money">¥' + formatNumber.format(amount) + '</span>';
  const isPaid = order => order.payment === 'Paid';
  const lineCents = item => Math.round(item.unit * 100) * item.qty;
  const orderTotal = order => order.items.reduce((sum, item) =>
    sum + (item.status === 'Cancelled' ? 0 : lineCents(item)), 0) / 100;
  const dateText = (day) => new Date(day + 'T12:00:00').toLocaleDateString('en-GB', { weekday:'short', day:'numeric', month:'short' });
  const minute = (time) => Number(time.slice(0,2)) * 60 + Number(time.slice(3));
  const timeAt = minutes => String(Math.floor(minutes / 60)).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0');
  const bookingsOn = day => reservations.filter(record => record.day === day);
  const liveTable = table => occupancy.find(record => record.table === table);
  const roles = { customer:'Customer', frontdesk:'Front desk', kitchen:'Kitchen', admin:'Administrator' };
  const categories = { burgers:'Burgers', pizzas:'Pizzas', sides:'Sides', drinks:'Drinks' };
  const legacyCategories = new Map([
    ['芝士牛肉堡','burgers'], ['双层招牌堡','burgers'], ['番茄芝麻菜披萨','pizzas'],
    ['蘑菇白酱披萨','pizzas'], ['炸薯条','sides'], ['冰柠檬茶','drinks'],
  ]);
  const catalogByName = new Map(catalog.map(dish => [dish.name, dish.category]));
  const itemStatuses = { waiting:'Queued', cooking:'Cooking', ready:'Ready', served:'Served', cancelled:'Cancelled' };
  const paymentStatuses = { paid:'Paid', unpaid:'Unpaid', refunded:'Refunded', partially_refunded:'Partially refunded' };
  const categoryKey = (category, name) => category || legacyCategories.get(name) ||
    ({ burger:'burgers', pizza:'pizzas', sides:'sides', drinks:'drinks' })[catalogByName.get(name)];

  function shiftedDay(day, offset) {
    const date = new Date(day + 'T00:00:00Z');
    date.setUTCDate(date.getUTCDate() + offset);
    return date.toISOString().slice(0,10);
  }

  function localTimestamp(value) {
    const normalized = value.replace(' ', 'T');
    const utc = /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized) ? normalized : normalized + 'Z';
    return new Date(Date.parse(utc) + 8 * 60 * 60 * 1000).toISOString();
  }

  function elapsedMinutes(day, time) {
    return Math.max(0, Math.floor((Date.parse(serviceDate + 'T' + serviceTime + ':00Z') -
      Date.parse(day + 'T' + time + ':00Z')) / 60000));
  }

  const tableName = id => id == null ? '—' : layout[id - 1]?.[0] || 'T' + id;

  function normalizeOrders(rows) {
    return rows.map(row => {
      const placed = localTimestamp(row.created_at);
      const items = row.items.map(line => ({
        id: String(line.dish_id), qty:line.quantity, name:line.dish_name, unit:Number(line.unit_price),
        status:itemStatuses[line.status] || line.status, note:line.note,
        category:categories[categoryKey(line.category, line.dish_name)],
        inKitchen: ['waiting','cooking'].includes(line.queue_status),
        readyAt: line.queue_status === 'ready' && line.ready_at ? localTimestamp(line.ready_at) : '',
      }));
      const cancelled = row.status === 'cancelled';
      const status = cancelled ? 'Cancelled' : row.status === 'completed' ? 'Served' :
        items.some(item => ['Queued','Cooking'].includes(item.status)) ? 'In queue' :
          items.some(item => item.status === 'Ready') ? 'Ready' : 'In queue';
      return { id:String(row.order_id), table:tableName(row.table_id), day:placed.slice(0,10),
        time:placed.slice(11,16), status, active:row.status === 'active', items,
        payment:cancelled && row.payment_status === 'unpaid' ? 'Not required' :
          paymentStatuses[row.payment_status] || 'Unpaid' };
    });
  }

  function readReservations(bookings, visits) {
    const activeByBooking = new Map(visits.filter(visit => visit.booking_id).map(visit => [visit.booking_id,visit]));
    const matchedVisits = new Set();
    const reserved = bookings.map(booking => {
      const visit = booking.booking_date === serviceDate ? activeByBooking.get(booking.booking_id) : null;
      if (visit) matchedVisits.add(visit.visit_id);
      return { id:'b' + booking.booking_id, day:booking.booking_date,
        start:booking.starts_at.slice(0,5), end:booking.ends_at.slice(0,5),
        table:tableName(visit?.table_id || booking.table_id), guests:visit?.party_size || booking.party_size,
        name:booking.contact_name, phone:booking.phone_number,
        status:visit ? 'Seated' : booking.status === 'booked' ? 'Reserved' : 'Arrived',
        dietary:booking.dietary_note ? [{ text:booking.dietary_note }] : null, note:booking.note };
    });
    const walkIns = visits.filter(visit => !matchedVisits.has(visit.visit_id)).map(visit => {
      const arrived = localTimestamp(visit.arrived_at);
      const start = arrived.slice(0,10) === serviceDate ? arrived.slice(11,16) : '00:00';
      const end = timeAt(Math.min(1439, Math.max(minute(start) + 15, minute(serviceTime))));
      return { id:'v' + visit.visit_id, day:serviceDate, start, end,
        table:tableName(visit.table_id), guests:visit.party_size,
        name:visit.contact_name || 'Walk-in', phone:visit.phone_number, status:'Seated', walkIn:true };
    });
    const all = [...reserved,...walkIns].sort((a,b) => a.start.localeCompare(b.start));
    occupancy = [
      ...all.filter(entry => entry.day === serviceDate && entry.status === 'Seated'),
      ...all.filter(entry => entry.day === serviceDate && entry.status === 'Reserved' &&
        minute(entry.end) > minute(serviceTime)),
    ];
    return all;
  }

  function setFeedback(message = '') {
    feedback.textContent = message;
    feedback.hidden = !message;
  }

  async function request(url, fields) {
    const options = { headers:{ Accept:'application/json' }, cache:'no-store' };
    if (fields) {
      fields.set('csrf_token', csrf);
      options.method = 'POST';
      options.body = fields;
    }
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || !data.ok) {
      if (response.status === 401) throw new Error('Your session has ended. Sign in again to continue.');
      throw new Error(Object.values(data.errors || {}).flat().join(' ') ||
        data.message || 'The request could not be completed.');
    }
    return data;
  }

  async function refreshDishes() {
    const data = await request(root.dataset.dishesUrl);
    dishes = data.dishes.map(row => ({
      id:String(row.dish_id), name:row.dish_name, price:row.price,
      category:categories[categoryKey(row.category, row.dish_name)] || 'Uncategorized',
      prep:row.prep_time_minutes, ingredients:row.ingredients,
      status:row.is_archived ? 'Archived' : row.is_available ? 'Available' : 'Unavailable',
    }));
  }

  async function refreshAccounts() {
    const data = await request(root.dataset.accountsUrl);
    accounts = [
      ...data.customers.map(row => ({
        id:'customer-' + row.customer_phone, name:row.name, role:roles.customer, phone:row.customer_phone,
        status:row.is_active ? 'Active' : 'Inactive', editable:false,
      })),
      ...data.staff.map(row => ({
        id:String(row.staff_id), name:row.name, role:roles[row.role] || row.role,
        roleKey:row.role, phone:row.phone, email:row.email, status:row.is_active ? 'Active' : 'Inactive',
        editable: row.role === 'frontdesk' || row.role === 'kitchen',
      })),
    ];
  }

  async function refreshWorkspace() {
    const data = await request(root.dataset.workspaceUrl);
    const previousDate = serviceDate;
    serviceDate = data.service_date;
    serviceTime = data.service_time;
    weekDays = Array.from({length:7}, (_,index) => shiftedDay(serviceDate,index - 6));
    const all = normalizeOrders(data.orders);
    weekOrders = all.filter(order => order.day >= weekDays[0] && order.day <= serviceDate);
    orders = weekOrders.filter(order => order.day === serviceDate);
    kitchenOrders = all.filter(order => order.active);
    orderDays = new Set(data.order_days);
    floor = data.tables.map(row => {
      const position = layout[row.table_id - 1];
      return { id:tableName(row.table_id), seats:row.capacity, x:position?.[2], y:position?.[3] };
    });
    reservations = readReservations(data.bookings, data.visits);
    if (!loaded || (previousDate !== serviceDate && state.date === previousDate)) {
      state.date = serviceDate;
      state.calendarMonth = serviceDate.slice(0,7) + '-01';
    }
    if (!loaded || (previousDate !== serviceDate && state.orderDate === previousDate)) {
      state.orderDate = serviceDate;
    }
    if (!floor.some(table => table.id === state.table)) state.table = occupancy[0]?.table || floor[0]?.id || '';
    if (state.orderDate === serviceDate) {
      ledgerOrders = orders;
      ledgerDate = serviceDate;
    }
    const clock = root.querySelector('[data-service-clock]');
    clock.dateTime = serviceDate + 'T' + serviceTime + ':00+08:00';
    clock.textContent = dateText(serviceDate) + ' ' + serviceTime;
  }
  const selected = (value) => value ? ' aria-pressed="true"' : ' aria-pressed="false"';
  const active = (value) => value ? ' aria-current="page"' : '';
  const title = (label, text = '') => '<div class="dp-heading"><div class="dp-heading-title"><h1>' + label +
    '</h1><div class="dp-heading-rule" aria-hidden="true"></div></div>' + text + '</div>';
  const head = (label, text = '') => '<div class="dp-section-top"><h2>' + label + '</h2>' + text + '</div>';
  const more = (label, target, extra = '') => '<button class="dp-link" type="button" data-view="' + target + '" ' + extra + '>' + label + '</button>';
  const toolbarSelect = (field, name, options, value, placeholder) =>
    '<label>' + name + '<select data-filter="' + field + '"><option value="">' + placeholder + '</option>' +
    options.map(option => '<option' + (option === value ? ' selected' : '') + '>' + es(option) + '</option>').join('') +
    '</select></label>';
  const tableHead = (labels) => '<thead><tr>' + labels.map(label =>
    '<th scope="col"' + (label === 'Total' || label === 'Price' ? ' class="dp-right"' : '') + '>' + label + '</th>').join('') + '</tr></thead>';
  function stat(label, value, caption, routeLabel, target, extra = '') {
    return '<button class="dp-stat" type="button" data-view="' + target + '" ' + extra + '>' +
      '<span class="dp-stat-data"><span class="dp-stat-label">' + label + '</span><strong class="dp-number">' +
      value + '</strong><small>' + caption + '</small></span><span class="dp-stat-route"><span>' +
      routeLabel + '</span><span class="dp-arrow" aria-hidden="true">→</span></span></button>';
  }
  const salesGroups = [
    { id:'burgers', label:'Burgers', categories:['Burgers'] },
    { id:'pizzas', label:'Pizzas', categories:['Pizzas'] },
    { id:'sides-drinks', label:'Sides & drinks', categories:['Sides','Drinks'] },
  ];
  const shortDayFormat = new Intl.DateTimeFormat('en-GB', {day:'numeric', month:'short', timeZone:'UTC'});
  const shortDay = day => shortDayFormat.format(new Date(day + 'T00:00:00Z'));
  function salesBuckets(range, metric) {
    const weekly = range === 'week';
    const lastHour = Math.floor(minute(serviceTime) / 60);
    const startHour = orders.reduce((hour, order) => Math.min(hour, Number(order.time.slice(0,2))),
      Math.min(11, lastHour));
    const keys = weekly ? weekDays : Array.from({length:lastHour - startHour + 1},
      (_,index) => timeAt((startHour + index) * 60));
    const buckets = keys.map(key => ({ label:weekly ? shortDay(key) : key, amounts:salesGroups.map(() => 0) }));
    const byKey = new Map(keys.map((key,index) => [key,buckets[index].amounts]));
    for (const order of weekly ? weekOrders : orders) {
      if (order.status === 'Cancelled' || (metric === 'revenue' && !isPaid(order))) continue;
      const key = weekly ? order.day : order.time.slice(0,2) + ':00';
      const amounts = byKey.get(key);
      if (!amounts) continue;
      const touched = new Set();
      for (const item of order.items) {
        if (item.status === 'Cancelled') continue;
        const index = salesGroups.findIndex(group => group.categories.includes(item.category));
        if (index < 0) continue;
        if (metric === 'revenue') amounts[index] += lineCents(item);
        else touched.add(index);
      }
      for (const index of touched) amounts[index]++;
    }
    return metric === 'revenue' ? buckets.map(bucket => ({
      ...bucket, amounts:bucket.amounts.map(cents => cents / 100),
    })) : buckets;
  }
  function salesChart(range) {
    const weekly = range === 'week';
    const metric = state.salesMetric[range];
    const revenue = metric === 'revenue';
    const buckets = salesBuckets(range, metric);
    const display = value => (revenue ? '¥' : '') + formatNumber.format(value);
    const maximum = Math.max(1,...buckets.flatMap(bucket => bucket.amounts));
    const roughStep = maximum / 4;
    const scale = Math.max(1, 10 ** Math.floor(Math.log10(roughStep)));
    const step = ([1,2,5,10].find(factor => factor * scale >= roughStep) || 10) * scale;
    const ticks = Math.ceil(maximum / step);
    const left = 54;
    const width = weekly ? 710 : 470;
    const edge = width - 26;
    const pitch = (edge - left) / Math.max(1, buckets.length - 1);
    const x = index => left + index * pitch;
    const y = value => 127 - value / (ticks * step) * 111;
    const grid = Array.from({length:ticks + 1}, (_,index) => {
      const value = index * step;
      return '<line class="dp-grid" x1="' + left + '" x2="' + edge + '" y1="' + y(value) + '" y2="' + y(value) + '"></line>' +
        '<text x="' + (left - 9) + '" y="' + (y(value) + 3) + '" text-anchor="end">' + display(value) + '</text>';
    }).join('');
    const curves = salesGroups.map((group,seriesIndex) => {
      const points = buckets.map((bucket,index) => [x(index),y(bucket.amounts[seriesIndex])]);
      // Using horizontal handles keeps each segment within its two measured values.
      const path = points.slice(1).map(([endX,endY],index) => {
        const [startX,startY] = points[index];
        const middle = (startX + endX) / 2;
        return ' C ' + middle + ' ' + startY + ' ' + middle + ' ' + endY + ' ' + endX + ' ' + endY;
      }).join('');
      return '<path class="dp-sales-line" data-series="' + group.id + '" d="M ' + points[0].join(' ') + path + '"></path>' +
        points.map(([px,py]) => '<circle class="dp-sales-node" data-series="' + group.id + '" cx="' +
          px + '" cy="' + py + '" r="' + (seriesIndex === 2 ? 1.8 : 2.35) + '"></circle>').join('');
    }).join('');
    const labels = buckets.map((bucket,index) => weekly || index % 2 === 0 ? '<text x="' + x(index) +
      '" y="148" text-anchor="middle">' + es(bucket.label) + '</text>' : '').join('');
    const hitAreas = buckets.map((bucket,index) => {
      const label = bucket.label + ' · ' + salesGroups.map((group,groupIndex) =>
        group.label + ' ' + display(bucket.amounts[groupIndex]) + (revenue ? '' : ' orders')).join(' · ');
      return '<rect class="dp-sales-hit" x="' + (x(index) - pitch / 2) + '" y="10" width="' +
        pitch + '" height="120"><title>' + es(label) + '</title></rect>';
    }).join('');
    const legend = salesGroups.map((group,index) => '<li data-series="' + group.id + '"><i aria-hidden="true"></i>' +
      es(group.label) + ' <strong class="dp-number">' + display(
        buckets.reduce((sum,bucket) => sum + bucket.amounts[index],0)) + '</strong></li>').join('');
    const toggles = '<div class="dp-segmented" role="group" aria-label="Sales metric">' +
      [['orders','Orders'],['revenue','Revenue']].map(([key,label]) =>
        '<button type="button" data-sales-range="' + range + '" data-sales-metric="' + key + '"' +
        selected(key === metric) + '>' + label + '</button>').join('') + '</div>';
    const period = weekly ? shortDay(weekDays[0]) + '–' + shortDay(serviceDate) + ' · Last 7 days' :
      'Today · ' + buckets[0].label + '–' + serviceTime + ' · Hourly';
    const uncategorized = (weekly ? weekOrders : orders).some(order =>
      order.status !== 'Cancelled' && (!revenue || isPaid(order)) &&
      order.items.some(item => item.status !== 'Cancelled' && !item.category));
    const description = (revenue ? 'Paid items at order prices · by order time.' :
      'Orders counted once per category. Cancelled orders excluded.') +
      (uncategorized ? ' Uncategorized items are excluded.' : '');
    return '<section class="dp-panel dp-sales-panel' + (weekly ? ' dp-sales-week' : '') + '" data-sales-panel="' +
      range + '">' + head(weekly ? 'Weekly sales by category' : 'Sales by category',toggles) +
      '<p class="dp-caption dp-sales-range">' + period + ' · ' + (revenue ? 'CNY' : 'Order count') +
      '</p><svg class="dp-plot" viewBox="0 0 ' + width + ' 156" role="img" aria-label="' +
      es((revenue ? 'Paid revenue in CNY' : 'Order count') + ' by category. ' + period) +
      '">' + grid + curves + labels + hitAreas + '</svg><ul class="dp-sales-legend" aria-label="Category totals">' +
      legend + '</ul><p class="dp-caption">' + description + '</p></section>';
  }
  function dishRankingRings(leaders) {
    const center = 116;
    const start = -Math.PI / 2;
    const sweep = 3 * Math.PI / 2;
    const limit = Math.max(10, Math.ceil(leaders[0][1] / 10) * 10);
    const point = (radius, angle) => [center + radius * Math.cos(angle), center + radius * Math.sin(angle)]
      .map(value => value.toFixed(2));
    const arc = (radius, fraction) => {
      const angle = sweep * fraction;
      return 'M ' + center + ' ' + (center - radius) + ' A ' + radius + ' ' + radius + ' 0 ' +
        Number(angle > Math.PI) + ' 1 ' + point(radius, start + angle).join(' ');
    };
    const rings = leaders.map(([name, qty], index) => {
      const rank = index + 1;
      const radius = 90 - index * 15;
      return '<path class="dp-dish-ring-track" d="' + arc(radius, 1) + '"></path>' +
        '<path class="dp-dish-ring" data-rank="' + rank + '" d="' + arc(radius, qty / limit) +
        '"><title>' + es(name + ' · ' + formatNumber.format(qty) + ' portions') + '</title></path>' +
        '<text class="dp-dish-ring-label" x="104" y="' + (center - radius + 4.5) +
        '" text-anchor="end">' + rank + '</text>';
    }).join('');
    const ticks = [0, .5, 1].map(fraction => {
      const angle = start + sweep * fraction;
      const [x1,y1] = point(96, angle);
      const [x2,y2] = point(102, angle);
      const [x,y] = point(110, angle);
      const anchor = fraction === 1 ? 'start' : 'middle';
      const labelY = fraction === 0 ? 12 : Number(y) + 4;
      return '<line class="dp-dish-ring-axis" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 +
        '" y2="' + y2 + '"></line><text class="dp-dish-ring-label" x="' + x + '" y="' + labelY +
        '" text-anchor="' + anchor + '">' + formatNumber.format(limit * fraction) + '</text>';
    }).join('');
    return '<svg class="dp-rose" viewBox="0 0 232 220" role="img" aria-label="Portions sold. ' +
      'Concentric arcs share a scale of 0 to ' + limit + ', ranked from outermost to innermost.">' +
      rings + ticks + '</svg>';
  }
  function popularDishes(paidOrders) {
    const volumes = new Map();
    for (const { items } of paidOrders) {
      for (const item of items) {
        if (item.status !== 'Cancelled') volumes.set(item.name, (volumes.get(item.name) || 0) + item.qty);
      }
    }
    const unavailable = dishes.filter(dish => dish.status === 'Unavailable');
    const ranked = [...volumes].sort((a,b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const options = '<div class="dp-segmented" role="group" aria-label="Number of dishes">' +
      [5,12].map(limit => '<button type="button" data-rose-limit="' + limit + '"' +
        selected(limit === state.roseLimit) + '>Top ' + limit + '</button>').join('') + '</div>';
    const header = '<section class="dp-panel" data-rose-panel>' + head('Popular dishes',options) +
      '<p class="dp-caption dp-rose-scope">Portions sold · paid orders today</p>';
    if (!ranked.length) return header + '<p class="dp-empty">No portions sold today.</p>' +
      (unavailable.length ? '<p class="dp-menu-foot"><strong>Unavailable now</strong> · ' +
        unavailable.map(dish => es(dish.name)).join(', ') + '</p>' : '') + '</section>';
    const modes = [5,12].map(limit =>
      '<div class="dp-dish-mode" data-rose-mode="' + limit + '" aria-hidden="' + (limit !== state.roseLimit) +
      '"' + (limit === state.roseLimit ? '' : ' inert') + '>' +
      popularDishMode(ranked.slice(0,limit), unavailable, limit === 5) + '</div>').join('');
    return header + '<div class="dp-dish-modes">' + modes + '</div></section>';
  }
  function popularDishMode(leaders, unavailable, showRings) {
    const shown = new Set(leaders.map(([name]) => name));
    const otherUnavailable = unavailable.filter(dish => !shown.has(dish.name));
    const unavailableNames = new Set(unavailable.map(dish => dish.name));
    const max = leaders[0][1];
    const footer = (otherUnavailable.length ? '<p class="dp-menu-foot"><strong>Also unavailable</strong> · ' +
      otherUnavailable.map(dish => es(dish.name)).join(', ') + '</p>' : '');
    const list = '<ol class="dp-rose-list' + (showRings ? ' dp-dish-rings' : '') + '" aria-label="Portions sold, ranked">' +
      leaders.map(([name,qty],index) =>
        '<li><span class="dp-rose-rank" aria-hidden="true">' + (index + 1) + '</span>' +
        '<span class="dp-rose-name">' + es(name) + (unavailableNames.has(name)
          ? '<small class="dp-unavailable-label">Unavailable now</small>' : '') +
        '</span><strong class="dp-number">' + formatNumber.format(qty) + '</strong></li>').join('') + '</ol>';
    if (showRings) {
      return '<div class="dp-rose-layout">' + dishRankingRings(leaders) + list + '</div>' + footer;
    }
    const step = 2 * Math.PI / leaders.length;
    const center = 116;
    const radius = 91;
    const gap = Math.min(.035, step * .08);
    const petalColors = ['#e2c898','#c7a676','#b69261','#a08051','#886a41','#c6aa84',
      '#b59a72','#a5865c','#97784e','#8d6d45','#a17e53','#765c3c'];
    const point = (r, angle) => [center + r * Math.cos(angle), center + r * Math.sin(angle)]
      .map(value => value.toFixed(2));
    const description = leaders.map(([name,qty]) => name + ': ' + qty + ' portions' +
      (unavailableNames.has(name) ? ', unavailable now' : '')).join('; ');
    const marks = leaders.map(([name,quantity],index) => {
      const middle = -Math.PI / 2 + index * step;
      const outer = (radius * Math.sqrt(quantity / max)).toFixed(2);
      const left = point(outer, middle - step / 2 + gap).join(' ');
      const right = point(outer, middle + step / 2 - gap).join(' ');
      const largeArc = step - 2 * gap > Math.PI ? 1 : 0;
      return '<path class="dp-rose-sector" style="--petal:' + petalColors[index] + '" d="M ' + center + ' ' +
        center + ' L ' + left + ' A ' + outer + ' ' + outer + ' 0 ' + largeArc + ' 1 ' +
        right + ' Z"><title>' + es(name + ' · ' + quantity + ' portions') + '</title></path>';
    }).join('');
    const labels = leaders.map((_,index) => {
      const [x,y] = point(radius + 12, -Math.PI / 2 + index * step);
      return '<text class="dp-rose-label" x="' + x + '" y="' + (Number(y) + 4).toFixed(2) +
        '" text-anchor="middle" aria-hidden="true">' + (index + 1) + '</text>';
    }).join('');
    return '<div class="dp-rose-layout"><svg class="dp-rose" viewBox="0 0 232 232" role="img" aria-label="' +
      es(description) + '"><circle class="dp-rose-grid" cx="' + center + '" cy="' + center + '" r="' + radius +
      '"></circle><circle class="dp-rose-grid" cx="' + center + '" cy="' + center + '" r="' +
      (radius * Math.sqrt(.5)).toFixed(2) + '"></circle>' + marks + labels +
      '</svg>' + list + '</div>' + footer;
  }
  function diningRoomSummary(occupied, reserved, readyOrders, upcoming, now) {
    const oldestReady = readyOrders[0];
    const age = oldestReady?.readyAt ? elapsedMinutes(oldestReady.readyAt.slice(0,10),
      oldestReady.readyAt.slice(11,16)) : null;
    const ready = oldestReady
      ? '<button type="button" class="dp-ready-callout" data-order="' + oldestReady.id +
        '"><span><strong>' + readyOrders.length + ' ready to serve</strong><span class="dp-ready-meta">Oldest · Table ' +
        oldestReady.table + ' · #' + oldestReady.id + '</span></span>' +
        (age === null ? '' : '<span class="dp-ready-age dp-number">' +
          age + ' min<small>since ready</small></span>') + '</button>'
      : '<p class="dp-caption">No orders ready to serve.</p>';
    const arrivals = new Map();
    for (const booking of upcoming) {
      if (!arrivals.has(booking.start)) arrivals.set(booking.start, []);
      arrivals.get(booking.start).push(booking);
    }
    const [nextTime, nextBookings] = arrivals.entries().next().value || [];
    const guestCount = bookings => bookings.reduce((sum, booking) => sum + booking.guests, 0);
    const arrivalSummary = (time, bookings) => time + ' · ' + guestCount(bookings) + ' guests';
    const slots = [...arrivals];
    let lastLabel = -8;
    const marks = slots.map(([time, bookings]) => {
      const offset = minute(time) - now;
      const hasLabel = offset >= 4 && offset <= 56 && offset - lastLabel >= 10;
      if (hasLabel) lastLabel = offset;
      return '<span class="dp-arrival-mark" style="--arrival-position:' + (offset / 60 * 100) +
        '%" title="' + es(arrivalSummary(time, bookings)) + '">' +
        (hasLabel ? '<time>' + time + '</time>' : '') + '</span>';
    }).join('');
    const arrivalList = nextBookings
      ? '<div class="dp-next-arrival"><time>' + nextTime + '</time><div class="dp-arrival-copy">' +
        '<p class="dp-caption">In ' + (minute(nextTime) - now) + ' min · ' + guestCount(nextBookings) + ' guests</p>' +
        '<div class="dp-arrival-tables">' + nextBookings.map(booking => '<button type="button" data-view="floor" data-booking="' +
          booking.id + '">Table ' + booking.table + '</button>').join('') + '</div></div></div>' +
        '<div class="dp-arrival-axis" role="img" aria-label="' +
        es(slots.map(([time, bookings]) => arrivalSummary(time, bookings)).join('; ')) + '">' + marks +
        '</div><div class="dp-arrival-ends"><span>Now · ' + serviceTime + '</span><span>+1 hour</span></div>'
      : '<p class="dp-caption">No bookings in the next hour.</p>';
    return '<section class="dp-panel" data-room-summary>' + head('Dining room', more('Open floor plan', 'floor')) +
      '<div class="dp-room-counts"><span>' + dot('sage') + '<strong>' + occupied +
      '</strong> Seated</span><span>' + dot('amber') + '<strong>' + reserved +
      '</strong> Reserved</span><span>' + dot('neutral') + '<strong>' + (floor.length - occupied - reserved) +
      '</strong> Available</span></div>' + ready +
      '<div class="dp-arrivals"><div class="dp-section-top"><h3>Arrivals · next hour</h3>' +
      more('Timeline', 'timeline', nextBookings ? 'data-booking="' + nextBookings[0].id + '"' : 'data-today') +
      '</div>' + arrivalList + '</div></section>';
  }
  function recentOrdersPanel(rows, now) {
    if (!rows.length) return '<section class="dp-panel" data-recent-orders>' +
      head('Recent orders', more('View all orders', 'orders', 'data-reset-orders')) +
      '<p class="dp-empty">No orders today.</p></section>';
    return '<section class="dp-panel" data-recent-orders>' +
      head('Recent orders', more('View all orders', 'orders', 'data-reset-orders')) +
      '<div class="dp-table-wrap dp-recent-orders"><table>' + tableHead(['Table / Order','Placed','Status','Total']) +
      '<tbody>' + rows.map(order => '<tr><td><button type="button" class="dp-record" data-order="' + order.id +
        '"><strong>Table ' + order.table + '</strong><small>#' + order.id + '</small></button></td><td>' +
        '<strong class="dp-number">' + (now - minute(order.time)) + ' min ago</strong><small><time>' +
        order.time + '</time></small></td><td>' + es(order.status) +
        '<br><span class="dp-tag dp-order-payment" data-tone="' + tone(order.payment) + '">' + es(order.payment) +
        '</span></td><td class="dp-right"><strong class="dp-recent-total">' + money(orderTotal(order)) +
        '</strong></td></tr>').join('') + '</tbody></table></div></section>';
  }
  function overview() {
    const tablesWithVisits = floor.map(table => liveTable(table.id));
    const occupied = tablesWithVisits.filter(booking => booking?.status === 'Seated').length;
    const reserved = tablesWithVisits.filter(booking => booking?.status === 'Reserved').length;
    const now = minute(serviceTime);
    const upcoming = bookingsOn(serviceDate).filter(booking =>
      booking.status === 'Reserved' && minute(booking.start) >= now && minute(booking.start) < now + 60);
    const { ready:readyOrders, prep:queuedOrders } = queueLanes();
    const queue = queuedOrders.reduce((sum,order) =>
      sum + order.items.filter(item => item.status === 'Queued').length, 0);
    const oldest = queuedOrders.reduce((age,order) => Math.max(age, elapsedMinutes(order.day, order.time)), 0);
    const paidOrders = orders.filter(isPaid);
    const paidAmount = paidOrders.reduce((sum,order) => sum + orderTotal(order), 0);
    const upcomingGuests = upcoming.reduce((sum,booking) => sum + booking.guests, 0);
    const firstBooking = upcoming[0];
    return title(titles.overview) +
      '<section class="dp-summary" aria-label="Current service figures">' +
      stat('Occupied tables', occupied + ' / ' + floor.length, (floor.length - occupied - reserved) +
        ' available now', 'Floor plan', 'floor') +
      stat('Items awaiting prep', queue, queuedOrders.length ? 'Oldest order placed ' + oldest + ' min ago' :
        'No orders in preparation', 'Kitchen queue', 'queue') +
      stat('Orders today', orders.length, paidOrders.length + ' paid · ' + money(paidAmount), 'Orders', 'orders', 'data-reset-orders') +
      stat('Guests in next hour', upcomingGuests, firstBooking
        ? upcoming.length + ' bookings · Next at ' + firstBooking.start : 'No upcoming bookings',
        'Reservation timeline', 'timeline', firstBooking ? 'data-booking="' + firstBooking.id + '"' : 'data-today') + '</section>' +
      '<div class="dp-overview-grid">' + diningRoomSummary(occupied, reserved, readyOrders, upcoming, now) +
      salesChart('today') + '</div><div class="dp-overview-grid dp-overview-lower">' +
      recentOrdersPanel(orders.slice(0,5), now) + popularDishes(paidOrders) + '</div>';
  }
  function filteredOrders() {
    return ledgerOrders.filter(order => (!state.orderStatus || order.status === state.orderStatus) &&
      (!state.payment || order.payment === state.payment));
  }
  function currentOrder(rows) {
    const current = rows.find(order => order.id === state.order) || rows[0];
    state.order = current?.id || '';
    return current;
  }
  function orderTable(rows) {
    if (ledgerLoading) return '<p class="dp-empty" role="status">Loading orders…</p>';
    if (ledgerError) return '<p class="dp-empty" role="alert">' + es(ledgerError) +
      ' <button type="button" class="dp-link" data-retry-orders>Retry</button></p>';
    if (!rows.length) return '<p class="dp-empty">No orders match these filters.</p>';
    return '<div class="dp-table-wrap dp-ledger dp-order-scroll"><table>' +
      tableHead(['Order','Table','Placed','Status','Payment','Total']) + '<tbody>' + rows.slice(0,state.orderLimit).map(order =>
      '<tr data-order-row="' + order.id + '"' + (state.order === order.id ? ' class="dp-selected"' : '') +
      '><td><button type="button" class="dp-record dp-number" aria-controls="dp-order-details" data-order="' + order.id +
      '"' + selected(state.order === order.id) + '>#' + order.id + '</button></td><td>' + order.table +
      '</td><td><time datetime="' + order.day + 'T' + order.time + ':00">' + order.time + '</time>' +
      (!state.orderDate ? '<span class="dp-ledger-caption">' + shortDay(order.day) + '</span>' : '') +
      '</td><td>' + tag(order.status) + '</td><td>' + tag(order.payment) +
      '</td><td class="dp-right dp-ledger-value">' + money(orderTotal(order)) + '</td></tr>').join('') +
      '</tbody></table></div>' + (rows.length > state.orderLimit ?
        '<button type="button" class="dp-link" data-more-orders>Show more orders</button>' : '');
  }
  function orderDetail(order) {
    const panel = '<aside class="dp-panel dp-detail" id="dp-order-details">';
    if (!order) return panel + head('Order details') +
      '<p class="dp-caption">Select an order to see its items and payment status.</p></aside>';
    return panel + head('Order #' + order.id) + tag(order.status) +
      '<dl><div><dt>Table</dt><dd>' + order.table + '</dd></div><div><dt>Placed</dt><dd><time datetime="' +
      order.day + 'T' + order.time + ':00">' + order.time + '</time><div class="dp-caption">' +
      orderDateLabel.format(new Date(order.day + 'T00:00:00Z')) + '</div></dd></div><div><dt>Payment</dt><dd>' + tag(order.payment) +
      '</dd></div></dl><div class="dp-detail-block"><h3>Items</h3>' +
      order.items.map(item => '<div class="dp-line-item"><span>' + item.qty + ' × ' + es(item.name) + '</span>' +
        money(item.qty * item.unit) + '</div><p>' + es(item.status) + (item.note ? ' · ' + es(item.note) : '') + '</p>').join('') +
      '<div class="dp-detail-total"><span>Total</span><strong>' + money(orderTotal(order)) + '</strong></div></div></aside>';
  }
  function orderDateText() {
    return state.orderDate ? orderDateLabel.format(new Date(state.orderDate + 'T00:00:00Z')) : 'All dates';
  }
  function renderOrderCalendar(panel, day) {
    const month = day.slice(0,7) + '-01';
    const monthDate = new Date(month + 'T00:00:00Z');
    const monthName = orderMonthLabel.format(monthDate);
    const lead = (monthDate.getUTCDay() + 6) % 7;
    panel.dataset.orderCalendar = month;
    const days = Array.from({length:42},(_,index) => {
      const date = shiftedDay(month,index - lead);
      const hasOrders = orderDays.has(date);
      return '<button type="button" class="dp-order-day" data-order-day="' + date + '" aria-label="' +
        orderDateLabel.format(new Date(date + 'T00:00:00Z')) + (hasOrders ? ', orders available' : '') + '"' +
        selected(state.orderDate === date) + (hasOrders ? ' data-has-orders' : '') +
        (date.slice(0,7) !== month.slice(0,7) ? ' data-other-month' : '') +
        (date === serviceDate ? ' aria-current="date"' : '') + '>' + Number(date.slice(-2)) + '</button>';
    }).join('');
    panel.innerHTML =
      '<div class="dp-order-month"><button type="button" data-order-month-step="-1" aria-label="Previous month">‹</button>' +
      '<strong aria-live="polite">' + monthName + '</strong><button type="button" data-order-month-step="1" aria-label="Next month">›</button></div>' +
      '<div class="dp-calendar" role="group" aria-label="' + monthName + '">' +
      ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(name => '<span class="dp-calendar-label">' + name + '</span>').join('') +
      days + '</div><div class="dp-order-calendar-footer"><button type="button" class="dp-link" data-order-day="">All dates</button>' +
      '<span class="dp-order-calendar-key">· Orders available</span><button type="button" class="dp-link" data-order-day="' +
      serviceDate + '">Service day</button></div>';
  }
  function setOrderCalendarOpen(control, open, restoreFocus = false) {
    const toggle = control.querySelector('[data-order-date-toggle]');
    const panel = control.querySelector('[data-order-calendar]');
    toggle.setAttribute('aria-expanded',String(open));
    panel.hidden = !open;
    if (open) {
      const day = state.orderDate || serviceDate;
      renderOrderCalendar(panel,day);
      panel.querySelector('.dp-order-day[data-order-day="' + day + '"]').focus({preventScroll:true});
    } else if (restoreFocus) {
      toggle.focus({preventScroll:true});
    }
  }
  function ordersPage() {
    const rows = ledgerDate === state.orderDate ? filteredOrders() : [];
    const current = ledgerDate === state.orderDate && !ledgerError ? currentOrder(rows) : null;
    return title(titles.orders) + salesChart('week') +
      '<div class="dp-split"><section class="dp-panel"><div class="dp-toolbar">' +
      '<div class="dp-order-date" data-order-date><span id="dp-order-date-label" class="dp-ledger-caption">Order date</span>' +
      '<button type="button" class="dp-order-date-toggle" data-order-date-toggle aria-expanded="false" aria-controls="dp-order-calendar"' +
      ' aria-labelledby="dp-order-date-label dp-order-date-value"><span id="dp-order-date-value" class="dp-number">' +
      orderDateText() + '</span><span class="dp-calendar-icon" aria-hidden="true"></span></button>' +
      '<div id="dp-order-calendar" class="dp-order-calendar" role="group" aria-label="Order date picker" data-order-calendar hidden></div></div>' +
      toolbarSelect('orderStatus','Order status',['In queue','Ready','Served','Cancelled'],state.orderStatus,'All statuses') +
      toolbarSelect('payment','Payment',['Paid','Unpaid','Not required','Refunded','Partially refunded'],state.payment,'All payments') +
      '</div><div data-order-results>' + orderTable(rows) + '</div></section>' + orderDetail(current) + '</div>';
  }
  function queueFoodArt(item) {
    const categoryArt = { Burgers:queueArt.burger, Pizzas:queueArt.pizza, Drinks:queueArt.tea };
    const art = /sparkling water|气泡水/i.test(item.name) ? queueArt.water :
      /fries|薯条/i.test(item.name) ? queueArt.fries : categoryArt[item.category];
    if (art) return '<img src="' + art + '" alt="">';
    return /onion rings|洋葱圈/i.test(item.name) ? '<span class="dp-plate-rings"></span>' : '';
  }
  function ticket(order, ready) {
    const items = order.items.filter(item => item.status !== 'Cancelled');
    const readyTime = ready && order.readyAt;
    const time = readyTime ? readyTime.slice(11,16) : order.time;
    const day = readyTime ? readyTime.slice(0,10) : order.day;
    const elapsed = elapsedMinutes(day,time);
    const age = readyTime ? 'Ready for ' + elapsed + ' min' :
      ready ? 'Placed ' + elapsed + ' min ago' : 'Waiting ' + elapsed + ' min';
    const artItems = items.map(item => ({ item, art:queueFoodArt(item) })).filter(entry => entry.art);
    const illustrated = items.length > 4 || artItems.length < items.length ? artItems.slice(0,3) : artItems;
    const extra = items.length - illustrated.length;
    const plated = illustrated.map(({ item, art }) => '<span class="dp-plate-item">' + art +
      (item.qty > 1 ? '<b class="dp-plate-qty">×' + item.qty + '</b>' : '') + '</span>').join('') +
      (extra ? '<span class="dp-plate-more">+' + extra + '</span>' : '');
    const receipt = items.map(item => '<li><strong>' + item.qty + '×</strong><div>' + es(item.name) +
      (item.note ? '<span class="dp-receipt-note">' + es(item.note) + '</span>' : '') +
      (item.status === 'Cooking' ? '<span class="dp-receipt-ready">Cooking</span>' : '') + '</div></li>').join('');
    return '<article class="dp-ticket"><div class="dp-ticket-head"><div><h3>' +
      '<button type="button" class="dp-record" data-order="' + order.id + '" aria-label="Table ' + order.table +
      ', order #' + order.id + '">Table ' + order.table + '</button></h3><span class="dp-caption" aria-hidden="true">#' + order.id +
      '</span></div><div class="dp-ticket-time"><strong class="dp-ticket-age dp-number">' + age +
      '</strong><time class="dp-caption" datetime="' + day + 'T' + time + ':00+08:00">' +
      (readyTime ? 'Ready at ' : 'Placed at ') + time + '</time></div></div>' +
      '<div class="dp-ticket-body"><div class="dp-ticket-plate" aria-hidden="true"><img class="dp-plate-image" src="' +
      queueArt.plate + '" alt=""><div class="dp-plate-items" data-count="' + (illustrated.length + Number(Boolean(extra))) +
      '">' + plated + '</div></div><div class="dp-receipt"><div class="dp-receipt-labels" aria-hidden="true">' +
      '<span>Qty</span><span>Item</span></div><ul aria-label="Order items">' + receipt + '</ul></div></div></article>';
  }
  function queueLanes() {
    const ready = [];
    const prep = [];
    for (const order of kitchenOrders) {
      const readyItems = order.items.filter(item => item.status === 'Ready');
      const prepItems = order.items.filter(item => item.inKitchen && ['Queued','Cooking'].includes(item.status));
      if (readyItems.length) ready.push({ ...order, items:readyItems,
        readyAt:readyItems.map(item => item.readyAt).filter(Boolean).sort()[0] || '' });
      if (prepItems.length) prep.push({ ...order, items:prepItems });
    }
    ready.sort((a,b) => (a.readyAt || a.day + 'T' + a.time).localeCompare(b.readyAt || b.day + 'T' + b.time));
    return { ready, prep:prep.reverse() };
  }

  function queuePage() {
    const { ready, prep } = queueLanes();
    const waiting = prep.reduce((sum,order) => sum + order.items.length, 0);
    return title(titles.queue, '<span class="dp-caption">Read-only view</span>') +
      '<div class="dp-queue"><section class="dp-panel dp-queue-lane" data-queue-lane="ready">' +
      head('Ready to serve', '<span class="dp-caption">' + ready.length + ' orders</span>') +
      (ready.map(order => ticket(order,true)).join('') || '<p class="dp-empty">No dishes ready to serve.</p>') +
      '</section><section class="dp-panel dp-queue-lane" data-queue-lane="prep">' +
      head('Awaiting preparation', '<span class="dp-caption">' + waiting + ' line items</span>') +
      (prep.map(order => ticket(order,false)).join('') || '<p class="dp-empty">No dishes in preparation.</p>') + '</section></div>';
  }
  function tableTabs() {
    return '<nav class="dp-tabs" aria-label="Tables views">' +
      [['floor','Floor plan'],['timeline','Timeline'],['calendar','Calendar']].map(([view,label]) =>
      '<button type="button" data-view="' + view + '"' + active(view === state.view) + '>' + label + '</button>').join('') +
      '</nav>';
  }
  function reservationDetail(record) {
    if (!record) {
      const table = state.view === 'floor' && floor.find(entry => entry.id === state.table);
      if (!table) return '<aside class="dp-panel dp-detail">' + head('Reservation details') +
        '<p class="dp-caption">Select a table or booking to view its details.</p></aside>';
      return '<aside class="dp-panel dp-detail">' + head('Table ' + es(table.id)) + tag('Available') +
        '<dl><div><dt>Capacity</dt><dd>' + table.seats + ' seats</dd></div></dl>' +
        '<p class="dp-caption">No reservation for this table on ' + dateText(state.view === 'floor' ? serviceDate : state.date) + '.</p></aside>';
    }
    const hasTable = floor.some(table => table.id === record.table);
    const action = state.view === 'timeline' && (record.day !== serviceDate || !hasTable) ? '' : state.view === 'timeline'
      ? more('Locate on floor plan', 'floor', 'data-booking="' + record.id + '"')
      : more('Locate in timeline', 'timeline', 'data-booking="' + record.id + '"');
    const guestInfo = record.dietary ? '<div class="dp-detail-block"><h3>Dietary information</h3>' +
      record.dietary.map(detail => detail.type === 'Allergy'
        ? '<p class="dp-note"><span class="dp-allergy">Allergy</span>' + es(detail.text) + '</p>'
        : '<p>' + es(detail.text) + '</p>').join('') +
      '</div>' : '';
    return '<aside class="dp-panel dp-detail">' + head('Table ' + record.table, '<span class="dp-caption">' +
      (record.walkIn ? 'Current visit' : 'Reservation') + '</span>') + tag(record.status) +
      '<dl><div><dt>' + (record.walkIn ? 'Arrived' : 'Booked time') + '</dt><dd><time>' + record.start + '</time></dd></div><div><dt>Party size</dt><dd>' +
      record.guests + ' guests</dd></div><div><dt>Guest</dt><dd>' + es(record.name) + '</dd></div>' +
      (record.phone ? '<div><dt>Contact</dt><dd>' + es(record.phone) + '</dd></div>' : '') + '</dl>' + guestInfo +
      (record.note ? '<div class="dp-detail-block"><h3>Visit note</h3><p>' + es(record.note) + '</p></div>' : '') +
      action + '</aside>';
  }
  function floorSeat(table) {
    const entry = liveTable(table.id);
    const label = entry?.status || 'Available';
    const short = label === 'Seated' ? entry.guests + ' guests' : label === 'Reserved' ? entry.start : table.seats + ' seats';
    const chairs = Array.from({length:table.seats}, (_,index) => {
      const columns = Math.ceil(table.seats / 2);
      return '<i class="dp-chair" aria-hidden="true" data-side="' + (index < columns ? 'top' : 'bottom') +
        '" style="--chair-x:' + (index % columns + 1) * 100 / (columns + 1) + '%"></i>';
    }).join('');
    return '<button type="button" class="dp-seat" data-table="' + table.id + '" data-capacity="' + table.seats +
      '"' + (table.x == null ? '' : ' style="--x:' + table.x + '%;--y:' + table.y + '%"') + selected(state.table === table.id) +
      ' aria-label="Table ' + table.id + ', ' + label + ', ' + short + '">' + chairs + '<strong>' + table.id +
      '</strong>' + tag(label) + '<small>' + short + '</small></button>';
  }
  function floorPage() {
    const hasLayout = floor.length && floor.every(table => table.x != null);
    return title(titles.floor) + tableTabs() + '<div class="dp-split"><section class="dp-panel">' +
      head('Dining room', '<span class="dp-caption">Today · ' + serviceTime + '</span>') +
      '<div class="dp-floor' + (hasLayout ? '' : ' dp-floor-grid') + '" role="group" aria-label="Dining room floor plan">' +
      (hasLayout ? '<span class="dp-floor-zone dp-zone-window">Window seats</span><span class="dp-floor-zone dp-zone-door">Entrance</span>' +
      '<span class="dp-floor-zone dp-zone-bar">Service bar</span>' : '') +
      (floor.map(floorSeat).join('') || '<p class="dp-empty">No tables have been configured.</p>') +
      '</div><div class="dp-key">' + ['Available','Reserved','Seated'].map(tag).join('') +
      '</div></section>' + reservationDetail(liveTable(state.table)) + '</div>';
  }
  function timelinePage() {
    const bookings = bookingsOn(state.date);
    const trackStart = bookings.reduce((start,booking) =>
      Math.min(start, Math.floor(minute(booking.start) / 60) * 60),11 * 60);
    const trackEnd = bookings.reduce((end,booking) =>
      Math.max(end, Math.ceil(minute(booking.end) / 60) * 60),21 * 60);
    const trackSpan = trackEnd - trackStart;
    const tickCount = 5;
    const trackPosition = time => (minute(time) - trackStart) / trackSpan * 100;
    const now = trackPosition(serviceTime);
    const showNow = state.date === serviceDate && now >= 0 && now < 100;
    const tableIds = new Set(floor.map(table => table.id));
    const rows = bookings.some(booking => !tableIds.has(booking.table)) ? [...floor,{ id:'—' }] : floor;
    const bands = table => bookings.filter(booking => (tableIds.has(booking.table) ? booking.table : '—') === table.id).map(booking => {
      const start = trackPosition(booking.start);
      const length = Math.max(0.5,trackPosition(booking.end) - start);
      return '<button type="button" class="dp-booking-band" data-booking="' + booking.id + '" data-tone="' + tone(booking.status) +
        '" style="--begin:' + start + '%;--span:' + length +
        '%"' + selected(booking.id === state.booking) + ' aria-label="Table ' + table.id + ', ' + booking.start +
        ' to ' + booking.end + ', ' + es(booking.name) + ', ' + booking.guests + ' guests">' +
        es(booking.name) + ' · ' + booking.guests + '</button>';
    }).join('');
    const current = bookings.find(booking => booking.id === state.booking);
    const ticks = Array.from({ length:tickCount }, (_,i) =>
      '<time>' + timeAt(Math.floor(trackStart + i * trackSpan / tickCount)) + '</time>').join('');
    return title(titles.timeline) + tableTabs() + '<div class="dp-split"><section class="dp-panel dp-schedule" style="--now:' +
      now + '%;--hour-gap:' + 100 / tickCount + '%">' +
      head(dateText(state.date), more('Choose a date', 'calendar')) +
      (showNow ? '<div class="dp-now-label"><span>Now ' + serviceTime + '</span></div>' : '') +
      '<div class="dp-hours"><span></span><div class="dp-hour-track">' + ticks + '</div></div>' +
      rows.map(table => '<div class="dp-timeline-row" data-selected="' + (table.id === state.table) +
        '"><span class="dp-row-label">' + table.id + '</span><div class="dp-time-track">' +
        (showNow ? '<span class="dp-now" aria-hidden="true"></span>' : '') +
        bands(table) + '</div></div>').join('') +
      '<div class="dp-key">' + ['Seated','Reserved','Arrived'].map(tag).join('') + '</div></section>' + reservationDetail(current) + '</div>';
  }
  function calendarPage() {
    const bookings = bookingsOn(state.date).filter(booking => !booking.walkIn);
    const month = new Date(state.calendarMonth + 'T00:00:00Z');
    const monthName = orderMonthLabel.format(month);
    const lead = (month.getUTCDay() + 6) % 7;
    const prefix = state.calendarMonth.slice(0,7);
    const days = new Date(Date.UTC(month.getUTCFullYear(),month.getUTCMonth() + 1,0)).getUTCDate();
    const counts = new Map();
    for (const booking of reservations) {
      if (!booking.walkIn && booking.day.startsWith(prefix))
        counts.set(booking.day,(counts.get(booking.day) || 0) + 1);
    }
    const dateCells = Array.from({length:Math.ceil((lead + days) / 7) * 7},(_,index) => {
      const day = index - lead + 1;
      if (day < 1 || day > days) return '<span aria-hidden="true"></span>';
      const iso = prefix + '-' + String(day).padStart(2,'0');
      const count = counts.get(iso) || 0;
      return '<button type="button" class="dp-day" data-date="' + iso + '"' + selected(iso === state.date) +
        ' aria-label="' + dateText(iso) + ', ' + count + ' bookings"><span>' + day + '</span>' +
        (count ? '<small>' + count + ' ' + (count === 1 ? 'booking' : 'bookings') + '</small>' : '') + '</button>';
    }).join('');
    const description = bookings.length ? '<ul class="dp-booking-list">' + bookings.map(booking =>
      '<li><button type="button" data-view="timeline" data-booking="' + booking.id + '"><time>' + booking.start +
      '</time> · Table ' + booking.table + '</button><p>' + es(booking.name) + ' · ' + booking.guests + ' guests</p></li>').join('') +
      '</ul>' : '<p class="dp-empty">No bookings for this date.</p>';
    return title(titles.calendar) + tableTabs() + '<div class="dp-split"><section class="dp-panel">' +
      head(monthName, '<div class="dp-order-month"><button type="button" data-calendar-step="-1" aria-label="Previous month">‹</button>' +
        '<button type="button" data-calendar-step="1" aria-label="Next month">›</button></div>') +
      '<div class="dp-calendar" aria-label="' + monthName + ' reservations calendar">' +
      ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day => '<span class="dp-calendar-label">' + day + '</span>').join('') +
      dateCells + '</div></section><aside class="dp-panel dp-detail">' +
      head(dateText(state.date), '<span class="dp-caption">' + bookings.length + ' bookings</span>') +
      description + more('Open day timeline', 'timeline', 'data-scheduled-day') + '</aside></div>';
  }
  function accountsPage() {
    const rows = accounts.filter(entry => !state.role || entry.role === state.role);
    const current = rows.find(entry => entry.id === state.account);
    return title(titles.accounts, '<div class="dp-heading-tools"><button type="button" class="dp-button dp-primary" data-new-account>New staff account</button></div>') +
      '<div class="dp-split"><section class="dp-panel"><div class="dp-toolbar">' +
      toolbarSelect('role','Role',Object.values(roles),state.role,'All roles') +
      '</div><div class="dp-table-wrap dp-ledger"><table>' + tableHead(['Name','Role','Status']) + '<tbody>' + rows.map(entry =>
      '<tr' + (state.account === entry.id ? ' class="dp-selected"' : '') +
      '><td><button type="button" class="dp-record" data-account="' + es(entry.id) + '">' + es(entry.name) +
      '</button></td><td>' + es(entry.role) + '</td><td>' + tag(entry.status) + '</td></tr>').join('') +
      '</tbody></table></div></section>' +
      '<aside class="dp-panel dp-detail">' + (state.account === 'new' || (state.accountEditing && current?.editable) ? accountForm(current) : current ?
        head(es(current.name)) + tag(current.status) + '<dl><div><dt>Role</dt><dd>' + es(current.role) +
        '</dd></div></dl><div class="dp-detail-block"><h3>Contact</h3><p>' + es(current.email || current.phone || '—') + '</p></div>' +
        (!current.editable ? '<p class="dp-caption">Read-only account</p>' :
          '<div class="dp-account-actions"><button class="dp-button" type="button" data-edit-account>Edit account</button>' +
          (current.status === 'Active' ? '<button class="dp-button dp-danger" type="button" data-deactivate-account>Deactivate</button>' : '') + '</div>')
        : head('Account details') + '<p class="dp-caption">Select an account to see its details.</p>') +
      '</aside></div>';
  }
  function accountForm(account) {
    return head(account ? 'Edit staff account' : 'New staff account') + '<form class="dp-form" data-admin-account-form>' +
      '<label>Name<input name="name" value="' + es(account?.name || '') + '" maxlength="100" required autocomplete="off"></label>' +
      '<label>Role<select name="role"><option value="frontdesk">Front desk</option><option value="kitchen"' +
      (account?.roleKey === 'kitchen' ? ' selected' : '') + '>Kitchen</option></select></label>' +
      '<label>Phone number<input name="phone_number" type="tel" value="' + es(account?.phone || '') + '" required autocomplete="off"></label>' +
      '<label>Email address<input name="email" type="email" value="' + es(account?.email || '') + '" required autocomplete="off"></label>' +
      (account ? '' : '<label>Password<input name="password" type="password" minlength="6" required autocomplete="new-password"></label>') +
      '<p data-action-feedback role="alert" hidden></p>' +
      '<div class="dp-account-actions"><button type="button" class="dp-button" data-cancel-account>Cancel</button>' +
      '<button type="submit" class="dp-button dp-primary">Save account</button></div></form>';
  }
  function dishForm(dish) {
    return head(dish ? 'Edit dish' : 'New dish') + '<form class="dp-form" data-admin-dish-form>' +
      (dish ? tag(dish.status) : '') +
      '<label>Dish name<input name="name" value="' + es(dish?.name || '') + '" maxlength="100" required autocomplete="off"></label>' +
      '<label>Category<select name="category"><option value="">Uncategorized</option>' +
      Object.entries(categories).map(([key,label]) => '<option value="' + key + '"' +
        (label === dish?.category ? ' selected' : '') + '>' + label + '</option>').join('') +
      '</select></label><label>Price (¥)<input name="price" type="number" min="' + (dish ? '0' : '0.01') +
      '" step="0.01" value="' + (dish?.price ?? '') + '" required></label>' +
      '<label>Preparation (min)<input name="prep_time_minutes" type="number" min="1" step="1" value="' +
      (dish?.prep ?? '') + '" required></label>' +
      '<label>Ingredients<textarea name="ingredients" maxlength="1000" rows="2">' +
      es(dish?.ingredients || '') + '</textarea></label><p data-action-feedback role="alert" hidden></p>' +
      '<div class="dp-account-actions"><button type="submit" class="dp-button dp-primary">Save dish</button>' +
      (dish && dish.status !== 'Archived' ?
        '<button type="button" class="dp-button dp-danger" data-archive-dish>Archive dish</button>' : '') + '</div></form>';
  }
  function filteredDishes() {
    return dishes.filter(dish => (!state.category || dish.category === state.category) &&
      (!state.dishStatus || dish.status === state.dishStatus));
  }
  function dishList(rows) {
    if (!rows.length) return '<p class="dp-empty">No dishes match these filters.</p>';
    return '<table>' + tableHead(['Dish','Prep','Status','Price']) +
      '<tbody>' + rows.map(dish => '<tr' + (state.dish === dish.id ? ' class="dp-selected"' : '') +
      '><td><button type="button" class="dp-record" data-dish="' + dish.id + '">' + es(dish.name) +
      '</button><div class="dp-ledger-caption">' + es(dish.category) + '</div></td><td class="dp-number">' + dish.prep +
      ' min</td><td>' + tag(dish.status) + '</td><td class="dp-right dp-ledger-value">' + money(dish.price) + '</td></tr>').join('') +
      '</tbody></table>';
  }
  function dishDetail(rows) {
    const current = rows.find(dish => dish.id === state.dish);
    if (current || state.dish === 'new') {
      return { id:state.dish, markup:dishForm(current) };
    }
    return { id:'', markup:head('Dish details') + '<p class="dp-caption">Select a dish to inspect it.</p>' };
  }
  function updateDishDetail(rows) {
    const detail = main.querySelector('[data-dish-detail]');
    const next = dishDetail(rows);
    if (detail.dataset.dishDetail === next.id) return;
    detail.dataset.dishDetail = next.id;
    detail.setAttribute('data-updated','');
    detail.innerHTML = next.markup;
  }
  function dishesPage() {
    const rows = filteredDishes();
    const detail = dishDetail(rows);
    return title(titles.dishes, '<div class="dp-heading-tools"><button type="button" class="dp-button dp-primary" data-new-dish>New dish</button></div>') +
      '<div class="dp-split"><section class="dp-panel"><div class="dp-toolbar">' +
      toolbarSelect('category','Category',[...Object.values(categories),'Uncategorized'],state.category,'All categories') +
      toolbarSelect('dishStatus','Menu status',['Available','Unavailable','Archived'],state.dishStatus,'All statuses') +
      '</div><div class="dp-table-wrap dp-ledger dp-dish-list" data-dish-list>' + dishList(rows) +
      '</div></section><aside class="dp-panel dp-detail" data-dish-detail="' + detail.id + '">' +
      detail.markup + '</aside></div>';
  }
  const views = { overview, orders:ordersPage, queue:queuePage, floor:floorPage, timeline:timelinePage,
    calendar:calendarPage, accounts:accountsPage, dishes:dishesPage };
  const tableViews = { tables:'floor', 'tables/timeline':'timeline', 'tables/calendar':'calendar' };
  const sections = { floor:'tables', timeline:'tables/timeline', calendar:'tables/calendar' };

  function go(view) {
    navigate(sections[view] || view);
  }

  function show(view, focus = false) {
    state.view = view;
    main.innerHTML = loaded ? views[view]() :
      title(titles[view]) + '<p class="dp-empty" role="status">' +
      (loading ? 'Loading restaurant data…' : '<button type="button" class="dp-link" data-retry-workspace>Retry loading</button>') + '</p>';
    const section = view === 'timeline' || view === 'calendar' ? 'floor' : view;
    root.querySelectorAll('.dp-sidebar [data-view]').forEach(button => {
      if (button.dataset.view === section) button.setAttribute('aria-current','page');
      else button.removeAttribute('aria-current');
    });
    if (focus) {
      const heading = main.querySelector('h1');
      heading.setAttribute('tabindex', '-1');
      heading.focus({preventScroll:true});
      heading.scrollIntoView({block:'nearest'});
    }
  }

  function openSection(section, focus) {
    const view = tableViews[section] || section;
    show(view,focus);
    if (!loaded || Date.now() - refreshedAt > 30000) loadWorkspace();
    else if (view === 'orders') loadLedger();
  }

  function loadWorkspace() {
    if (loading) return loading;
    loading = Promise.all([refreshWorkspace(), refreshAccounts(), refreshDishes()]).then(() => {
      loaded = true;
      refreshedAt = Date.now();
      setFeedback();
      if (!main.contains(document.activeElement) || !document.activeElement.closest('form,[data-order-date]')) {
        show(state.view);
        if (state.view === 'orders') loadLedger();
      }
    }).catch(error => {
      setFeedback(error.message);
      if (!loaded) {
        loading = null;
        show(state.view);
      }
    }).finally(() => { loading = null; });
    if (!loaded) show(state.view);
    return loading;
  }

  async function loadLedger(force = false) {
    const day = state.orderDate;
    if (!force && ledgerDate === day) return;
    const serial = ++ledgerRequest;
    ledgerLoading = true;
    ledgerError = '';
    ledgerOrders = [];
    ledgerDate = null;
    refreshOrderResults();
    try {
      const path = day ? root.dataset.orderUrl + '?date=' + encodeURIComponent(day) : root.dataset.orderUrl;
      const data = await request(path);
      if (serial !== ledgerRequest || state.orderDate !== day) return;
      ledgerOrders = normalizeOrders(data.orders);
      ledgerDate = day;
    } catch (error) {
      if (serial === ledgerRequest && state.orderDate === day) ledgerError = error.message;
    } finally {
      if (serial === ledgerRequest) {
        ledgerLoading = false;
        refreshOrderResults();
      }
    }
  }

  function setUserProfileOpen(open) {
    userButton.setAttribute('aria-expanded', String(open));
    userProfile.hidden = !open;
  }

  function openConfirmation(title, name, label, action) {
    pendingAction = action;
    deactivation.querySelector('h2').textContent = title;
    deactivation.querySelector('[data-deactivation-name]').textContent = name;
    deactivation.querySelector('[data-confirm-deactivate]').textContent = label;
    deactivation.querySelector('[data-action-feedback]').hidden = true;
    deactivation.showModal();
  }

  async function adminAction(container, button, url, fields, complete) {
    const errorOutput = container.querySelector('[data-action-feedback]');
    errorOutput.hidden = true;
    button.disabled = true;
    try {
      const data = await request(url,fields);
      complete(data);
    } catch (error) {
      errorOutput.textContent = error.message;
      errorOutput.hidden = false;
    } finally {
      button.disabled = false;
    }
  }
  function refreshOrderResults() {
    if (state.view !== 'orders' || !main.querySelector('[data-order-results]')) return;
    const rows = filteredOrders();
    const current = ledgerLoading || ledgerError ? null : currentOrder(rows);
    main.querySelector('[data-order-results]').innerHTML = orderTable(rows);
    main.querySelector('#dp-order-details').outerHTML = orderDetail(current);
  }
  function selectOrder(id) {
    const source = state.view === 'orders' ? ledgerOrders : state.view === 'queue' ? kitchenOrders : [...orders,...kitchenOrders];
    const order = source.find(entry => entry.id === id);
    if (!order) return;
    if (state.view !== 'orders') {
      state.order = id;
      state.orderDate = order.day;
      state.orderStatus = '';
      state.payment = '';
      state.orderLimit = 100;
      go('orders');
      return;
    }
    if (state.order === id) return;
    const row = main.querySelector('[data-order-row="' + id + '"]');
    if (!row) return;
    const previous = main.querySelector('[data-order-row].dp-selected');
    if (previous) {
      previous.classList.remove('dp-selected');
      previous.querySelector('[data-order]').setAttribute('aria-pressed','false');
    }
    state.order = id;
    row.classList.add('dp-selected');
    row.querySelector('[data-order]').setAttribute('aria-pressed','true');
    main.querySelector('#dp-order-details').outerHTML = orderDetail(order);
  }
  root.addEventListener('keydown', (event) => {
    const openCalendar = main.querySelector('[data-order-calendar]:not([hidden])');
    if (openCalendar) {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOrderCalendarOpen(openCalendar.closest('[data-order-date]'),false,true);
        return;
      }
      const offset = { ArrowLeft:-1, ArrowRight:1, ArrowUp:-7, ArrowDown:7 }[event.key];
      const day = event.target.closest('.dp-order-day')?.dataset.orderDay;
      if (offset && day) {
        event.preventDefault();
        const next = shiftedDay(day,offset);
        if (next.slice(0,7) !== openCalendar.dataset.orderCalendar.slice(0,7)) renderOrderCalendar(openCalendar,next);
        openCalendar.querySelector('.dp-order-day[data-order-day="' + next + '"]').focus({preventScroll:true});
        return;
      }
    }
    if (event.key !== 'Escape' || userProfile.hidden) return;
    setUserProfileOpen(false);
    userButton.focus();
  });
  root.addEventListener('click', (event) => {
    if (!userProfile.hidden && !userMenu.contains(event.target)) setUserProfileOpen(false);
    const dateControl = event.target.closest('[data-order-date]');
    const openCalendar = main.querySelector('[data-order-calendar]:not([hidden])');
    if (!dateControl && openCalendar) setOrderCalendarOpen(openCalendar.closest('[data-order-date]'),false);
    const button = event.target.closest('button');
    if (!button) {
      const row = event.target.closest('[data-order-row]');
      if (row) selectOrder(row.dataset.orderRow);
      return;
    }
    if ('orderDateToggle' in button.dataset) {
      setOrderCalendarOpen(dateControl,button.getAttribute('aria-expanded') !== 'true',true);
      return;
    }
    if ('orderMonthStep' in button.dataset) {
      const panel = dateControl.querySelector('[data-order-calendar]');
      const month = new Date(panel.dataset.orderCalendar + 'T00:00:00Z');
      const step = button.dataset.orderMonthStep;
      month.setUTCMonth(month.getUTCMonth() + Number(step));
      renderOrderCalendar(panel,month.toISOString().slice(0,10));
      panel.querySelector('[data-order-month-step="' + step + '"]').focus({preventScroll:true});
      return;
    }
    if ('orderDay' in button.dataset) {
      setOrderCalendarOpen(dateControl,false,true);
      const day = button.dataset.orderDay;
      if (day === state.orderDate) return;
      state.orderDate = day;
      state.orderLimit = 100;
      dateControl.querySelector('#dp-order-date-value').textContent = orderDateText();
      loadLedger();
      return;
    }
    if ('retryOrders' in button.dataset) {
      loadLedger(true);
      return;
    }
    if ('moreOrders' in button.dataset) {
      const scroll = main.querySelector('.dp-order-scroll').scrollTop;
      state.orderLimit += 100;
      refreshOrderResults();
      main.querySelector('.dp-order-scroll').scrollTop = scroll;
      (main.querySelector('[data-more-orders]') || main.querySelector('.dp-order-scroll button:last-child'))?.focus({preventScroll:true});
      return;
    }
    if ('retryWorkspace' in button.dataset) {
      loadWorkspace();
      return;
    }
    if (button === userButton) {
      setUserProfileOpen(userProfile.hidden);
      return;
    }
    if ('salesMetric' in button.dataset) {
      const { salesRange, salesMetric } = button.dataset;
      state.salesMetric[salesRange] = salesMetric;
      main.querySelector('[data-sales-panel="' + salesRange + '"]').outerHTML = salesChart(salesRange);
      main.querySelector('[data-sales-metric="' + salesMetric + '"]').focus({preventScroll:true});
      return;
    }
    if ('roseLimit' in button.dataset) {
      const limit = Number(button.dataset.roseLimit);
      if (limit === state.roseLimit) return;
      state.roseLimit = limit;
      const panel = button.closest('[data-rose-panel]');
      for (const choice of panel.querySelectorAll('[data-rose-limit]')) {
        choice.setAttribute('aria-pressed', String(choice === button));
      }
      for (const mode of panel.querySelectorAll('[data-rose-mode]')) {
        const inactive = Number(mode.dataset.roseMode) !== limit;
        mode.inert = inactive;
        mode.setAttribute('aria-hidden', String(inactive));
      }
      return;
    }
    const { view, order, table, booking, date, account, dish } = button.dataset;
    if ('calendarStep' in button.dataset) {
      const month = new Date(state.calendarMonth + 'T00:00:00Z');
      const step = button.dataset.calendarStep;
      month.setUTCMonth(month.getUTCMonth() + Number(step));
      state.calendarMonth = month.toISOString().slice(0,10);
      const todayInMonth = serviceDate.startsWith(state.calendarMonth.slice(0,7));
      state.date = todayInMonth ? serviceDate : state.calendarMonth;
      state.booking = '';
      show('calendar');
      main.querySelector('[data-calendar-step="' + step + '"]').focus({preventScroll:true});
      return;
    }
    if ('closeDialog' in button.dataset) { button.closest('dialog').close(); return; }
    if ('deactivateAccount' in button.dataset) {
      const row = accounts.find(entry => entry.id === state.account && entry.editable);
      if (row) openConfirmation('Deactivate staff account?',row.name,'Deactivate', {
        url:root.dataset.staffUrl + '/' + row.id + '/deactivate',
        complete:() => { row.status = 'Inactive'; show('accounts'); },
      });
      return;
    }
    if ('archiveDish' in button.dataset) {
      const row = dishes.find(entry => entry.id === state.dish);
      if (row) openConfirmation('Archive dish?',row.name,'Archive', {
        url:root.dataset.dishesUrl + '/' + row.id + '/archive',
        complete:() => { row.status = 'Archived'; show('dishes'); },
      });
      return;
    }
    if ('confirmDeactivate' in button.dataset) {
      if (!pendingAction) return;
      const action = pendingAction;
      adminAction(deactivation,button,action.url,new FormData(),() => {
        deactivation.close();
        pendingAction = null;
        action.complete();
      });
      return;
    }
    if ('editAccount' in button.dataset || 'cancelAccount' in button.dataset) {
      state.accountEditing = 'editAccount' in button.dataset;
      if (!state.accountEditing && state.account === 'new') state.account = '';
      show('accounts');
      return;
    }
    if (order) {
      selectOrder(order);
    } else if (table) {
      state.table = table;
      state.booking = liveTable(table)?.id || '';
      state.date = serviceDate;
      go('floor');
      main.querySelector('[data-table="' + table + '"]')?.focus({preventScroll:true});
    } else if (booking) {
      const entry = reservations.find(row => row.id === booking);
      if (!entry) return;
      state.table = entry.table;
      state.booking = booking;
      state.date = entry.day;
      state.calendarMonth = state.date.slice(0,7) + '-01';
      go(view || 'timeline');
      if (!view) main.querySelector('[data-booking="' + booking + '"]')?.focus({preventScroll:true});
    } else if (date) {
      state.date = date;
      const first = bookingsOn(date)[0];
      state.booking = first?.id || '';
      state.table = first?.table || floor[0]?.id || '';
      show('calendar');
      main.querySelector('[data-date="' + date + '"]').focus({preventScroll:true});
    } else if (account !== undefined || 'newAccount' in button.dataset) {
      state.account = account === undefined ? 'new' : account;
      state.accountEditing = false;
      show('accounts');
    } else if (dish || 'newDish' in button.dataset) {
      state.dish = dish || 'new';
      for (const rowButton of main.querySelectorAll('[data-dish-list] [data-dish]')) {
        rowButton.closest('tr').classList.toggle('dp-selected', rowButton.dataset.dish === state.dish);
      }
      updateDishDetail(filteredDishes());
    } else if (view) {
      if ('resetOrders' in button.dataset) {
        state.orderDate = serviceDate;
        state.orderStatus = '';
        state.payment = '';
        state.orderLimit = 100;
      }
      if ('today' in button.dataset) {
        state.date = serviceDate;
        state.calendarMonth = serviceDate.slice(0,7) + '-01';
        state.table = floor[0]?.id || '';
        state.booking = '';
      }
      if (view === 'floor' && state.date !== serviceDate) {
        state.date = serviceDate;
        state.booking = liveTable(state.table)?.id || '';
      }
      go(view);
    }
  });
  root.addEventListener('change', (event) => {
    const filter = event.target.dataset.filter;
    if (!filter) return;
    state[filter] = event.target.value;
    if (filter === 'orderStatus' || filter === 'payment') {
      state.orderLimit = 100;
      refreshOrderResults();
      return;
    }
    if (filter === 'category' || filter === 'dishStatus') {
      const rows = filteredDishes();
      const list = main.querySelector('[data-dish-list]');
      list.setAttribute('data-updated','');
      list.innerHTML = dishList(rows);
      list.scrollTop = 0;
      updateDishDetail(rows);
      return;
    }
    if (filter === 'role') state.accountEditing = false;
    show(state.view);
    main.querySelector('[data-filter="' + filter + '"]').focus({preventScroll:true});
  });
  root.addEventListener('submit', (event) => {
    const form = event.target;
    const accountForm = form.matches('[data-admin-account-form]');
    if (!accountForm && !form.matches('[data-admin-dish-form]')) return;
    event.preventDefault();
    const accountId = state.account;
    const dishId = state.dish;
    const url = accountForm ?
      root.dataset.staffUrl + (accountId === 'new' ? '' : '/' + accountId + '/edit') :
      root.dataset.dishesUrl + (dishId === 'new' ? '' : '/' + dishId + '/edit');
    const save = form.querySelector('button[type="submit"]');
    if (save.disabled) return;
    adminAction(form,save,url,new FormData(form),data => {
      if (accountForm) {
        state.account = String(data.staff.staff_id);
        state.accountEditing = false;
        state.role = '';
        refreshAccounts().then(() => {
          if (state.view === 'accounts') show('accounts');
          setFeedback('Staff account saved.');
        }).catch(error => setFeedback('Staff account saved. ' + error.message));
      } else {
        state.dish = String(data.dish.dish_id);
        state.category = '';
        state.dishStatus = '';
        refreshDishes().then(() => {
          if (state.view === 'dishes') {
            show('dishes');
            confirmation.querySelector('[data-saved-dish]').textContent = data.dish.dish_name;
            confirmation.showModal();
          }
        }).catch(error => setFeedback('Dish saved. ' + error.message));
      }
    });
  });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && root.isConnected && Date.now() - refreshedAt > 30000) loadWorkspace();
  });
  return openSection;
}
