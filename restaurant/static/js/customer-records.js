// Business actions below use tab-local sample records until the role routes are integrated.
let records = { bookings: [], orders: [], visit: null };
let recordOwner;
let editingBooking = null;
let afterLogin = null;
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const localDate = date => [date.getFullYear(), String(date.getMonth()+1).padStart(2,'0'), String(date.getDate()).padStart(2,'0')].join('-');
const storageKey = owner => 'shuangfen.customer-preview.v1.' + owner;
// Restore earlier preview selections using the current menu names and assets.
const previousOptions = {
  '9 英寸':'9 inch', '12 英寸':'12 inch', '经典薄底':'Thin crust', '厚底':'Thick crust',
  '多加芝士':'Extra cheese', '多加蘑菇':'Extra mushrooms', '经典酱':'House sauce',
  '蒜香酱':'Garlic sauce', '不加酱':'No sauce', '多一片芝士':'Extra cheddar', '多一块牛肉饼':'Extra patty'
};
function restoreItem(row) {
  const dish = menu.find(item => item.id === row.dishId);
  if (!dish) return row;
  const labels = row.labels.map(label => previousOptions[label] ?? label);
  return {...row, name:dish.name, image:dish.image, labels,
    signature:JSON.stringify([dish.id, labels, row.note || ''])};
}
function loadCustomerRecords(user) {
  const owner = user ? user.role + ':' + user.username : 'guest';
  if (owner === recordOwner) return;
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem(storageKey(owner))) || {}; } catch {}
  const guestCart = recordOwner === 'guest' && user?.role === 'customer' ? state.cart : [];
  const cart = (saved.cart || []).map(restoreItem);
  for (const row of guestCart) {
    const match = cart.find(item => item.signature === row.signature);
    if (match) match.quantity = Math.min(maxCartQuantity,match.quantity + row.quantity);
    else cart.push({...row, id: Math.max(0,...cart.map(item=>item.id)) + 1});
  }
  if (guestCart.length) sessionStorage.removeItem(storageKey('guest'));
  recordOwner = owner;
  const orders = (saved.orders || []).map(order => ({...order, items:order.items.map(restoreItem)}));
  records = { bookings: saved.bookings || [], orders, visit: saved.visit || null };
  state.cart = cart; state.nextCartId = Math.max(0,...cart.map(item => item.id)) + 1;
  editingBooking = null;
  updateCartBadge();
}
function persistRecords() {
  if (recordOwner) sessionStorage.setItem(storageKey(recordOwner),JSON.stringify({...records,cart:state.cart}));
}
function resetBooking() {
  const today = new Date(), next = new Date(today); next.setDate(next.getDate()+1);
  const form = $('#reservation-form'); form.reset();
  $('#booking-date').min = localDate(today); $('#booking-date').value = localDate(next);
  $('#booking-form-title').textContent = 'Reserve a table'; $('#booking-feedback').textContent = '';
  editingBooking = null;
}
function showMyRecords() {
  $('#my-bookings').innerHTML = records.bookings.length ? records.bookings.map(b => `<article class="record"><strong>${escapeText(b.date)} · ${escapeText(b.slot)}</strong><p>${b.party} guests · ${b.cancelled ? 'Cancelled' : 'Reserved'}</p>${b.cancelled ? '' : `<button class="text-link" data-edit-booking="${b.id}">Modify</button><button class="text-link" data-cancel-booking="${b.id}">Cancel reservation</button>`}</article>`).join('') : '<p class="muted">No reservations yet.</p>';
  $('#my-orders').innerHTML = records.orders.length ? records.orders.map(o => `<article class="record"><strong>Table ${escapeText(o.table)} · ${money(o.total)}</strong><p>${o.paid ? 'Demo payment received' : 'Awaiting payment'} · ${escapeText(o.created)}</p><button class="text-link" data-order="${o.id}">Order details</button></article>`).join('') : '<p class="muted">No orders yet.</p>';
  $('#load-visit').textContent = records.visit ? 'Go to menu with sample visit' : 'Load sample visit';
}
$('#reservation-form').addEventListener('submit', e => {
  e.preventDefault();
  const form = e.currentTarget;
  $('#booking-date').min = localDate(new Date());
  if (!form.reportValidity()) return;
  if (currentUser()?.role !== 'customer') {
    if (isStaff(currentUser())) { $('#booking-feedback').textContent='Sign in with a customer account to reserve a table.'; return; }
    afterLogin = '#booking'; location.hash = 'account'; return;
  }
  const fields = new FormData(form);
  const values = {date:fields.get('booking_date'),party:Number(fields.get('party_size')),slot:fields.get('time_slot_id')};
  if (editingBooking) Object.assign(editingBooking,values);
  else records.bookings.unshift({id:crypto.randomUUID(),...values,cancelled:false});
  persistRecords();resetBooking();location.hash='account';
});
$('#my-bookings').addEventListener('click',e=>{
  const btn=e.target.closest('button'); if (!btn) return;
  const b=records.bookings.find(b=>b.id===(btn.dataset.editBooking || btn.dataset.cancelBooking));
  if (!b || b.cancelled) return;
  if (btn.hasAttribute('data-edit-booking')) {
    editingBooking=b;$('#booking-date').value=b.date;$('#booking-people').value=b.party;
    $('#reservation-form').elements.time_slot_id.value=b.slot;$('#booking-form-title').textContent='Edit reservation';location.hash='booking';
  } else {
    showRecord('Cancel this reservation?',`<p>${escapeText(b.date)} · ${escapeText(b.slot)} · ${b.party} guests</p><button class="button primary" id="cancel-confirm">Confirm cancellation</button>`);
    $('#cancel-confirm').onclick=()=>{b.cancelled=true;persistRecords();showMyRecords();closeDialog($('#record-dialog'));};
  }
});
function showRecord(title,markup) {
  $('#record-title').textContent=title;$('#record-content').innerHTML=markup;openDialog($('#record-dialog'));
}
function orderDetail(o,confirmPayment=false) {
  const lines=o.items.map(i=>`<article class="record"><strong>${escapeText(i.name)} × ${i.quantity}</strong><p>${i.labels.map(escapeText).join(' · ')} ${escapeText(i.note)}</p><p>Awaiting preparation · ${money(i.unitPrice*i.quantity)}</p></article>`).join('');
  showRecord(confirmPayment?'Confirm demo payment':'Order details',`<p>Sample visit · table ${escapeText(o.table)}</p>${lines}<div class="cart-grand-total"><b>${o.paid?'Demo payment received':'Total due'}</b><strong>${money(o.total)}</strong></div>${o.paid ? '<p>Payment reference '+escapeText(o.payment)+'</p>' : '<button class="button primary" id="pay-order">'+(confirmPayment?'Confirm payment of '+money(o.total):'Simulate payment')+'</button>'}`);
  if (!o.paid) $('#pay-order').onclick=()=>{
    if (confirmPayment) {o.paid=true;o.payment=crypto.randomUUID().slice(0,8);persistRecords();showMyRecords();}
    orderDetail(o,!confirmPayment);
  };
}
$('#my-orders').onclick=e=>{const o=records.orders.find(x=>x.id===e.target.closest('[data-order]')?.dataset.order);if(o)orderDetail(o);};
$('#load-visit').onclick=()=>{
  if(currentUser()?.role!=='customer')return;
  records.visit ||= {id:crypto.randomUUID(),table:'A2'};persistRecords();location.hash='menu';
};
$('#place-order').onclick=async()=>{
  if(!state.cart.length || !records.visit || currentUser()?.role!=='customer') return;
  const order={id:crypto.randomUUID(),visitId:records.visit.id,table:records.visit.table,created:new Date().toLocaleString('en-GB'),items:state.cart,paid:false,total:state.cart.reduce((sum,i)=>sum+i.unitPrice*i.quantity,0)};
  records.orders.unshift(order);state.cart=[];updateCartBadge();persistRecords();
  await closeDialog($('#cart-dialog'));location.hash='account';orderDetail(order);
};
$('#cart-account').onclick=()=>closeDialog($('#cart-dialog'));
