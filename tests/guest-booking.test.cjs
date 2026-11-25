const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = name => readFileSync(path.join(__dirname, '../restaurant/static/js/', name), 'utf8');
const guest = script('guest.js');
const take = (source, first, next) => source.slice(source.indexOf(first), source.indexOf(next));

function guestBooking(request) {
  const draft = { date: '2048-02-20', time: '1', guests: 2, table: 'A1' };
  const pending = { booking_date: draft.date, time_slot_id: draft.time, party_size: 2, table_id: 1,
    idempotency_key: 'original-attempt' };
  const persisted = [];
  const context = vm.createContext({
    reservationFlow: false, reservationBase: '/bookings',
    restaurantRequest: request, state: { draft }, pendingCreation: pending,
    editingBooking: null, editConflict: null, customerFeedback: '', customerRefreshVersion: 4,
    customerLoaded: false, focusedBookingId: null, app: { querySelector: () => null },
    tableIds: { A1: 1, A2: 2 }, tableLabel: id => 'A' + id, slots: { '1': '11:00-14:00' },
    bookingLabels: { booked: 'Reserved' },
    persist() { persisted.push(context.pendingCreation); },
  });
  vm.runInContext([
    take(guest, 'function bookingRecord(', 'function orderLines('),
    take(guest, 'function reservationFields(', 'function guestStatus('),
  ].join('\n'), context);
  const booking = { booking_id: 12, booking_date: draft.date, time_slot: '11:00-14:00', table_id: 1,
    party_size: 2, status: 'booked', version: 1 };
  return { context, draft, pending, persisted, booking };
}

test('a lost response remains recoverable after changing the draft to a new table', async () => {
  const calls = [];
  const fixture = guestBooking(async (url, fields) => {
    calls.push({ url, fields });
    if (calls.length === 1) throw new Error('The response was lost');
    return { booking: fixture.booking };
  });
  const { context, draft, pending, persisted } = fixture;
  await assert.rejects(context.resolveReservationCreation(), /Recover reservation/);
  assert.equal(context.pendingCreation, pending);
  draft.table = 'A2';
  await context.resolveReservationCreation();
  assert.deepEqual(calls, [
    { url: '/bookings', fields: pending },
    { url: '/bookings', fields: pending },
    { url: '/bookings/12/edit', fields: undefined },
  ]);
  assert.equal(context.state.booking.table, 'A1');
  assert.equal(context.editingBooking.version, 1);
  assert.equal(context.state.draft.table, 'A2');
  assert.equal(context.customerRefreshVersion, 5);
  assert.equal(context.pendingCreation, null);
  assert.deepEqual(persisted, [null]);
});

test('a lost details response keeps the same creation key for recovery', async () => {
  const fixture = guestBooking(async (url) => {
    if (url.endsWith('/edit')) throw new Error('Details unavailable');
    return { booking: fixture.booking };
  });
  await assert.rejects(fixture.context.resolveReservationCreation(), /was saved/);
  assert.equal(fixture.context.pendingCreation, fixture.pending);
});

test('an edit conflict loads the latest version while keeping the guest draft', async () => {
  const fixture = guestBooking(async () => ({ booking: { ...fixture.booking, table_id: 2, version: 2 } }));
  fixture.context.editingBooking = fixture.context.bookingRecord(fixture.booking);
  await fixture.context.loadCustomerEditConflict();
  assert.equal(fixture.context.editingBooking.version, 1);
  assert.equal(fixture.context.editConflict.latest.version, 2);
  assert.match(fixture.context.editConflict.message, /Table A2/);
  assert.equal(fixture.context.state.draft, fixture.draft);
  assert.equal(fixture.context.state.draft.table, 'A1');
});

test('a booking race tells the guest to choose another table', async () => {
  const context = vm.createContext({
    URLSearchParams,
    document: { querySelector: () => ({ content: 'csrf' }) },
    fetch: async () => ({
      ok: false, status: 409, headers: { get: () => 'application/json' },
      json: async () => ({ error: 'TABLE_UNAVAILABLE' }),
    }),
  });
  vm.runInContext(take(script('restaurant-api.js'), 'const restaurantCsrf', 'async function restaurantSeating'), context);
  await assert.rejects(context.restaurantRequest('/bookings', {}), {
    status: 409, code: 'TABLE_UNAVAILABLE', message: 'That table was just reserved. Choose another table.',
  });
});
