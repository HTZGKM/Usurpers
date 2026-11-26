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
