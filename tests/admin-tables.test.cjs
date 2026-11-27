const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const admin = readFileSync(path.join(__dirname, '../restaurant/static/js/admin.js'), 'utf8');
const section = (first, next) => admin.slice(admin.indexOf(first), admin.indexOf(next));

function adminTables(overrides) {
  const context = vm.createContext({
    reservationFlow: true,
    serviceDate: '2026-11-26', serviceTime: '09:00',
    state: { view: 'floor', date: '2026-11-26', table: 'A1' },
    titles: { floor: 'Tables', timeline: 'Tables' },
    liveTable: () => undefined,
    title: title => title,
    head: title => title,
    more: () => '',
    selected: current => ` aria-pressed="${current}"`,
    tableName: id => `A${id}`,
    orderDateLabel: new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }),
    historySelection: null,
    ...overrides,
  });
  vm.runInContext([
    section('const tones =', 'const state ='),
    section('const es =', 'const formatNumber ='),
    section('const dateText =', 'const bookingsOn ='),
    section('function localTimestamp(', 'const serviceMinute ='),
    section('function floorStatus(', 'function timelinePage('),
    section('function serviceTimeline(', 'function serviceCalendar('),
  ].join('\n'), context);
  return context;
}

test('floor plan distinguishes paused walk-ins from protection and dates the next reservation', () => {
  const floor = [
    { id: 'A1', seats: 2, status: 'reserved', reasonCode: 'closed',
      next: { booking_date: '2026-12-01', label: '11:00-14:00' } },
    { id: 'A2', seats: 2, status: 'reserved', reasonCode: 'reservation' },
    { id: 'A3', seats: 4, status: 'available' },
  ];
  const view = adminTables({ floor, tableTabs: () => '' });
  const html = view.floorPage();
  const closedTag = '<span class="dp-tag" data-tone="slate">No walk-ins</span>';
  const protectedTag = '<span class="dp-tag" data-tone="amber">Protected</span>';
  assert.match(view.floorSeat(floor[0]), /Table A1, No walk-ins, next reservation 1 Dec · 11:00-14:00/);
  assert.ok(view.floorSeat(floor[0]).includes(closedTag));
  assert.ok(view.floorSeat(floor[1]).includes(protectedTag));
  assert.match(view.floorSeat(floor[2]), /data-tone="neutral">Available/);
  const legend = html.slice(html.indexOf('class="dp-key"'), html.indexOf('</section>'));
  assert.ok(legend.includes(closedTag));
  assert.ok(legend.includes(protectedTag));
  assert.match(html, /<dt>Next reservation<\/dt><dd>1 Dec · 11:00-14:00/);
});

test('closed visits without a seating time stay on their recorded day and off the timeline scale', () => {
  const legacy = { visit_id: 1, table_id: 1, contact_name: 'Legacy visit', party_size: 2,
    status: 'closed', recorded_at: '2026-11-24T07:41:00Z', closed_at: '2026-11-26T00:42:00Z' };
  const active = { ...legacy, visit_id: 2, contact_name: 'Open legacy visit', status: 'seated', closed_at: null };
  const data = { server_now: '2026-11-26T01:00:00Z', tables: [{ table_id: 1 }],
    bookings: [], visits: [legacy, active] };
  const view = adminTables({ tableHistory: () => data, tableTabs: () => '' });
  const today = view.serviceTimeline();
  assert.match(today, /<time>11:00<\/time>/);
  assert.doesNotMatch(today, /<time>00:00<\/time>|data-history-record="v1"|dp-service-band/);
  assert.match(today, /data-history-record="v2"[^>]*>A1 · Open legacy visit<\/button> · Open/);

  view.state.date = '2026-11-24';
  view.historySelection = 'v1';
  const originalDay = view.serviceTimeline();
  assert.match(originalDay, /data-history-record="v1" aria-pressed="true"[^>]*>A1 · Legacy visit<\/button> · Closed/);
  assert.match(originalDay, /Seating time unknown · Visit recorded: Tue 24 Nov · 15:41/);
  assert.match(originalDay, /Table closed: Thu 26 Nov · 08:42/);
  assert.doesNotMatch(originalDay, /dp-service-band/);
});

function adminSales(overrides) {
  const context = vm.createContext({
    serviceDate: '2026-11-26', serviceTime: '09:14',
    serviceWindows: [['11:00','14:00'],['17:00','21:00']],
    historyDays: ['2026-11-18','2026-11-19','2026-11-20','2026-11-21','2026-11-22',
      '2026-11-23','2026-11-24','2026-11-25','2026-11-26'],
    state: { salesDays:30, salesMetric:{ today:'revenue', history:'orders' }, rosePeriod:'history', roseLimit:5 },
    orders: [], historyOrders: [], salesOrders: [], dishes: [],
    head: (title, options) => title + options,
    selected: current => ` aria-pressed="${current}"`,
    es: value => value,
    isPaid: order => order.payment === 'Paid',
    lineCents: item => item.unit * item.qty * 100,
    formatNumber: new Intl.NumberFormat('en'),
    compactNumber: new Intl.NumberFormat('en', { notation:'compact' }),
    popularDishMode: leaders => JSON.stringify(leaders),
    ...overrides,
  });
  vm.runInContext([
    section('const minute =', 'const bookingsOn ='),
    section('const salesGroups =', 'function dishRankingRings('),
    section('function popularDishes(', 'function popularDishMode('),
    section('function recentOrderLabel(', 'function orderDateText('),
  ].join('\n'), context);
  return context;
}

const paidBurger = { day:'2026-11-18', time:'12:07', paidDay:'2026-11-18', paidTime:'12:07', payment:'Paid', status:'Served',
  items:[{ name:'Burger', qty:3, unit:10, category:'Burgers', status:'Served' }] };

test('an uncategorized historical item does not inherit its current menu category', () => {
  const context = vm.createContext({
    localTimestamp:value => value || '', categories:{burgers:'Burgers'},
    categoryKey:() => 'burgers', itemStatuses:{served:'Served'}, paymentStatuses:{paid:'Paid'},
    tableName:() => 'A1',
  });
  vm.runInContext(section('function normalizeOrders(', 'function readReservations('),context);
  const [order] = context.normalizeOrders([{order_id:1,table_id:1,created_at:'2026-11-18T12:00:00',
    paid_at:'2026-11-18T13:00:00',status:'completed',payment_status:'paid',items:[
      {dish_id:1,dish_name:'Burger',category:null,quantity:1,unit_price:10,status:'served'}]}]);
  assert.equal(order.items[0].category,undefined);
});

test('today sales keep service hours and distinguish empty and incomplete service', () => {
  const view = adminSales({});
  const initial = view.salesBuckets('today', 'revenue');
  assert.equal(initial[0].label, '11:00');
  assert.equal(initial.at(-1).label, '21:00');
  assert.ok(initial.every(bucket => !bucket.visible));
  assert.match(view.salesChart('today'), /No paid sales recorded today/);
  assert.doesNotMatch(view.salesChart('today'), /class="dp-sales-node"/);

  view.serviceTime = '12:35';
  view.orders = [{ ...paidBurger, day:view.serviceDate }];
  view.salesOrders = [{ ...paidBurger, paidDay:view.serviceDate }];
  const current = view.salesBuckets('today', 'revenue');
  assert.equal(current[1].label, '12:00');
  assert.equal(current[1].amounts[0], 30);
  assert.equal(current[2].visible, false);
});

test('historical sales and popular dishes retain past paid orders when today has no orders', () => {
  const view = adminSales({ historyOrders:[paidBurger], salesOrders:[paidBurger] });
  assert.equal(view.salesBuckets('history', 'orders')[0].amounts[0], 1);
  assert.match(view.popularDishes(), /\[\["Burger",3\]\]/);
  view.state.rosePeriod = 'today';
  assert.match(view.popularDishes(), /No portions sold today/);
  view.state.salesDays = 7;
  assert.ok(view.salesBuckets('history', 'orders').every(bucket => bucket.amounts[0] === 0));
});

test('receipts follow payment date while order counts retain creation date', () => {
  const order = { ...paidBurger, paidDay:'2026-11-26', paidTime:'13:20' };
  const view = adminSales({ historyOrders:[order], salesOrders:[order], serviceTime:'14:00' });
  const receipts = view.salesBuckets('history','revenue');
  assert.equal(receipts[0].amounts[0],0);
  assert.equal(receipts.at(-1).amounts[0],30);
  const counts = view.salesBuckets('history','orders');
  assert.equal(counts[0].amounts[0],1);
  assert.equal(counts.at(-1).amounts[0],0);
  assert.equal(view.salesBuckets('today','revenue').find(bucket => bucket.label === '13:00').amounts[0],30);
  view.state.rosePeriod = 'today';
  assert.match(view.popularDishes(), /\[\["Burger",3\]\]/);
});

test('returning to the recent order range keeps the monthly rows when a date request finishes late', async () => {
  let finishDateRequest;
  const orders = [{ id:'1', day:'2026-11-25' }, { id:'2', day:'2026-11-24' }];
  const context = vm.createContext({
    recentOrderRange: 'recent', historyDays: Array(30), historyOrders: orders,
    state: { orderDate:'2026-11-24' }, ledgerDate: null, ledgerRequest: 0,
    ledgerOrders: [], ledgerLoading: false, ledgerError: '', invalidLedgerDates: 0,
    root: { dataset:{ orderUrl:'/admin/workspace/orders' } },
    refreshOrderResults() {},
    request: () => new Promise(resolve => { finishDateRequest = resolve; }),
    normalizeOrders: rows => rows,
  });
  vm.runInContext([
    section('function hasSpecificOrderDate(', 'function renderOrderCalendar('),
    section('async function loadLedger(', 'function setUserProfileOpen('),
  ].join('\n'), context);
  const pendingDate = context.loadLedger();
  context.state.orderDate = 'recent';
  await context.loadLedger();
  finishDateRequest({ orders:[orders[1]] });
  await pendingDate;
  assert.equal(context.orderDateText(), 'Last 30 days');
  assert.equal(context.hasSpecificOrderDate(), false);
  assert.equal(context.ledgerDate, 'recent');
  assert.equal(context.ledgerLoading, false);
  assert.equal(context.ledgerOrders, orders);
});
