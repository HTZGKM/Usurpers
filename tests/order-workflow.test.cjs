const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = name => readFileSync(path.join(__dirname, '../restaurant/static/js/', name), 'utf8');
const section = (source, first, next) => source.slice(source.indexOf(first), source.indexOf(next));

test('one kitchen order can show different dishes in all three lanes', async () => {
  const elements = new Map();
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, { innerHTML:'', textContent:'', dataset:{}, contains:() => false });
    return elements.get(selector);
  };
  const routes = [];
  const rows = ['waiting', 'cooking', 'ready'].map((status, index) => ({
    status, order_id:9005, order_type:'preorder', order_item_id:index + 1, dish_id:index + 1,
    quantity:index + 1, table_id:1,
  }));
  const workspace = { querySelector:element, addEventListener() {} };
  const context = vm.createContext({
    document:{ activeElement:null, addEventListener() {} }, setInterval() {},
    esc:value => value, tableLabel:() => 'A1',
    restaurantRequest:async url => {
      routes.push(url);
      return { items:url === '/kitchen/menu' ? [] : rows };
    },
  });
  vm.runInContext(script('kitchen.js'), context);
  context.mountKitchenWorkspace(workspace)('queue', false);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(routes, ['/kitchen/menu', '/kitchen/queue?status=active']);
  for (const [index, stage] of ['waiting','cooking','ready'].entries()) {
    const lane = element(`[data-kitchen-lane="${stage}"]`).innerHTML;
    assert.match(lane, /Preorder #9005/);
    assert.deepEqual([...lane.matchAll(/data-kitchen-line="(\d+)"/g)].map(match => Number(match[1])), [index + 1]);
    assert.equal(element(`[data-kitchen-stage="${stage}"]`).textContent, index + 1);
  }
  assert.equal(element('[data-kitchen-count]').textContent, '1 active order');
});

test('an unpaid past order still offers payment and a staged preorder explains the wait', () => {
  const api = script('restaurant-api.js');
  const guest = script('guest.js');
  const context = vm.createContext({
    esc:value => value, btn:(label, action) => `<button data-action="${action}">${label}</button>`,
    pair:() => '', mealLineMarkup:line => line.name,
  });
  vm.runInContext([
    section(api, 'function restaurantCanEditOrder(', 'function restaurantOrderEditor('),
    section(guest, 'function orderLines(', 'function customerPage('),
    section(guest, 'function renderSubmittedOrder(', 'function waitlistMarkup('),
  ].join('\n'), context);
  const item = { status:'waiting', dish_name:'Burger', quantity:1, estimated_ready_at:'2026-11-26 04:30:00' };
  const order = { status:'active', payment_status:'unpaid', order_type:'preorder', visit_id:5, items:[item] };
  assert.equal(context.orderLines(order)[0].labels[0], 'Scheduled · from 12:30');
  assert.equal(context.orderLines({ ...order, visit_id:null })[0].labels[0], 'Awaiting seating');
  assert.equal(context.orderLines({ ...order, items:[{ ...item, kitchen_status:'waiting' }] })[0].labels[0], 'Waiting for kitchen');
  const body = {};
  context.renderSubmittedOrder(body, { ...order, status:'completed', items:[{ ...item, status:'served' }] });
  assert.match(body.innerHTML, /pay-submitted-order/);
  context.renderSubmittedOrder(body, { ...order, visit_id:null });
  assert.doesNotMatch(body.innerHTML, /pay-submitted-order/);
});

test('the table bill includes only the open balance for the current visit', () => {
  const context = vm.createContext({ btn:(label, action) => `<button data-action="${action}">${label}</button>` });
  vm.runInContext([
    section(script('restaurant-api.js'), 'function restaurantCanPayOrder(', 'function restaurantPreorderWaiting('),
    section(script('guest.js'), 'function currentVisitBill(', 'function visitView('),
  ].join('\n'), context);
  const orders = [
    { order_id:9005, visit_id:5, status:'active', payment_status:'unpaid', total_amount:52 },
    { order_id:9006, visit_id:5, status:'completed', payment_status:'unpaid', total_amount:18 },
    { order_id:9007, visit_id:5, status:'completed', payment_status:'unpaid', total_amount:42 },
    { order_id:9008, visit_id:5, status:'active', payment_status:'paid', total_amount:10 },
    { order_id:9009, visit_id:4, status:'completed', payment_status:'unpaid', total_amount:65 },
    { order_id:9010, visit_id:5, status:'cancelled', payment_status:'unpaid', total_amount:20 },
  ];
  const bill = context.currentVisitBill({ visit_id:5 }, orders);
  assert.equal(bill.totalCents,11200);
  assert.deepEqual(Array.from(bill.orderIds),[9005,9006,9007]);
  assert.match(context.visitBillMarkup(bill), /3 unpaid orders for this visit.*Record ¥112\.00 payment/);
  assert.equal(context.currentVisitBill(null,orders),null);
  assert.doesNotMatch(context.visitBillMarkup(context.currentVisitBill({ visit_id:5 },[orders[3]])),/pay-visit/);
});

test('a lost order response is recovered with its original key and draft', async () => {
  const storage = new Map();
  const calls = [];
  const api = script('restaurant-api.js');
  const context = vm.createContext({
    document:{ querySelector:() => ({textContent:JSON.stringify({account:{role:'frontdesk',username:'desk'}})}) },
    sessionStorage:{getItem:k => storage.get(k) ?? null,setItem:(k,v) => storage.set(k,v),removeItem:k => storage.delete(k)},
    window:{confirm:() => true}, crypto:{randomUUID:() => 'first-draft'},
    restaurantRequest:async (_path,fields) => {
      calls.push(fields);
      if (calls.length === 1) throw new Error('connection lost');
      if (calls.length === 2) throw Object.assign(new Error('form expired'), {status:400, csrfExpired:true});
      return {order:{order_id:17}};
    },
  });
  vm.runInContext(section(api, 'const pendingRestaurantSubmissions', 'function restaurantOrderFields('), context);
  await assert.rejects(context.restaurantSubmitOnce('/frontdesk/orders', {visit_id:4,quantity:1}), /connection lost/);
  await assert.rejects(context.restaurantSubmitOnce('/frontdesk/orders', {visit_id:4,quantity:1}), /form expired/);
  assert.equal(storage.size, 1);
  const recovered = await context.restaurantSubmitOnce('/frontdesk/orders', {visit_id:4,quantity:2});
  assert.equal(recovered.recoveredPrevious, true);
  assert.equal(recovered.order.order_id, 17);
  assert.deepEqual(calls[0], calls[1]);
  assert.deepEqual(calls[0], calls[2]);
  assert.equal(calls[2].quantity, 1);
  assert.equal(storage.size, 0);
});
