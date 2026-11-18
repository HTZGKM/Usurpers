'use strict';

/* ==========================================================================
   工具函数*/
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const money = value => `¥${value}`;
const icons = () => window.lucide?.createIcons({ attrs: { 'aria-hidden': 'true' } });
const { imageBase, loginUrl, registerUrl, sessionUrl, logoutUrl } = document.body.dataset;
/* ==========================================================================
   数据与状态*/
const menu = [
  { id: 'burger', category: 'burger', name: 'House Cheeseburger', price: 38,
    description: 'Grilled beef, cheddar, lettuce, tomato and pickles.', extraPatty: true },
  { id: 'double', category: 'burger', name: 'Double Cheddar', price: 48,
    description: 'Two seared beef patties with aged cheddar.', extraPatty: true },
  { id: 'chicken', category: 'burger', name: 'Herb Chicken', price: 42,
    description: 'Herb-grilled chicken, butter lettuce and lemon yoghurt.' },
  { id: 'portobello', category: 'burger', name: 'Portobello', price: 40,
    description: 'Grilled portobello, baby greens and roasted garlic.' },
  { id: 'fish', category: 'burger', name: 'Crisp Fish', price: 46,
    description: 'Crumbed white fish, tartar sauce and shredded lettuce.' },
  { id: 'pizza', category: 'pizza', name: 'Margherita', price: 58,
    description: 'Blistered crust, tomato, mozzarella and fresh basil.' },
  { id: 'mushroom', category: 'pizza', name: 'Mushroom & Pepper', price: 62,
    description: 'Roasted mushrooms, sweet peppers and mozzarella over tomato.' },
  { id: 'bianca', category: 'pizza', name: 'Bianca', price: 60,
    description: 'A white pizza with ricotta, mozzarella and garden herbs.' },
  { id: 'olive', category: 'pizza', name: 'Olive & Oregano', price: 56,
    description: 'Black olives, tomato and oregano on a thin crust.' },
  { id: 'potato', category: 'pizza', name: 'Potato & Rosemary', price: 64,
    description: 'Thinly sliced potato, rosemary and a little sea salt.' },
  { id: 'fries', category: 'sides', name: 'Sea Salt Fries', price: 18,
    description: 'Sea salt, with tomato ketchup on the side.' },
  { id: 'onion', category: 'sides', name: 'Crispy Onion Rings', price: 22,
    description: 'Crisp onion rings with garlic sauce.', sold: true },
  { id: 'lemon', category: 'drinks', name: 'Lemon Soda', price: 16,
    description: 'Fresh lemon and sparkling water poured over ice.' },
  { id: 'tea', category: 'drinks', name: 'Iced Black Tea', price: 14,
    description: 'Lightly sweetened black tea, served over ice.' }
].map(dish => ({ ...dish, image: 'atelier/catalog/' + dish.id + '.webp' }));
const state = { category: 'burger', dish: null, quantity: 1, cart: [], editingCartId: null, nextCartId: 1 };
const maxCartQuantity = 99;
/* ==========================================================================
   动效基础设施*/
const desktopMotionMedia = matchMedia('(min-width:761px)');
const systemMotionMedia = matchMedia('(prefers-reduced-motion:reduce)');
const localMotions = new Map();
const dialogMotions = new WeakMap();
let dialogOverflow = null;

function reducedMotion() { return systemMotionMedia.matches; }
function desktopMotion() { return desktopMotionMedia.matches && !reducedMotion(); }
function cancelLocalMotion(element) {
  localMotions.get(element)?.cancel();
  localMotions.delete(element);
}
function revealLocal(element, duration = 200, distance = 8) {
  cancelLocalMotion(element);
  if (!element || !desktopMotion() || typeof element.animate !== 'function') return;
  const animation = element.animate([
    { opacity: .45, transform: `translateX(${distance}px)` },
    { opacity: 1, transform: 'translateX(0)' }
  ], { duration, easing: 'cubic-bezier(.2,.7,.2,1)' });
  localMotions.set(element, animation);
  const release = () => { if (localMotions.get(element) === animation) localMotions.delete(element); };
  animation.finished.then(release, release);
}
function settleReducedMotion() {
  if (desktopMotion()) return;
  localMotions.forEach(animation => animation.cancel());
  localMotions.clear();
  $$('dialog').forEach(dialog => {
    const motion = dialogMotions.get(dialog);
    if (!motion) return;
    if (motion.phase === 'closing') motion.finishClose?.();
    else if (motion.phase === 'opening') {
      ++motion.revision;
      stopDialogAnimation(motion);
      motion.phase = 'open';
      dialog.dataset.motionState = 'open';
    }
  });
}

/* ==========================================================================
   首页滚轮锁屏*/
const homeShowcase = $('#home-showcase');
const homePanels = $$('.home-panel');
const homeDots = $$('.home-dot');
const homeClosing = $('.customer-closing');
const homeState = { locked: false, wheelDelta: 0, lastWheel: 0 };
let homeScrollFrame = 0;
let homeUnlockTimer;

function homeRoute(view = (location.hash.slice(1) || 'index').split('/')[0]) {
  return view === 'home' || view === 'visit';
}
function homeStages() {
  return [...homePanels, homeClosing].filter(Boolean);
}
function homeStageTop(index) {
  const stage = homeStages()[index];
  if (!stage) return 0;
  return Math.max(0, Math.round(stage.getBoundingClientRect().top + window.scrollY));
}
function currentHomeStage() {
  const stages = homeStages();
  if (!stages.length) return 0;
  const current = window.scrollY;
  let closestIndex = 0;
  let closestDistance = Infinity;
  stages.forEach((stage, index) => {
    const distance = Math.abs(homeStageTop(index) - current);
    if (distance < closestDistance) {
      closestDistance = distance;
      closestIndex = index;
    }
  });
  return closestIndex;
}
function lockHomeScroll() {
  clearTimeout(homeUnlockTimer);
  homeState.locked = true;
  homeUnlockTimer = setTimeout(() => { homeState.locked = false; }, reducedMotion() ? 0 : 950);
}
function moveHomeStage(direction) {
  if (!homeRoute() || !homeShowcase || homeState.locked || $$('dialog').some(dialog => dialog.open)) return false;
  const stages = homeStages();
  if (!stages.length) return false;
  const current = currentHomeStage();
  const next = Math.max(0, Math.min(stages.length - 1, current + direction));
  if (next === current) return false;
  lockHomeScroll();
  window.scrollTo({ top: homeStageTop(next), behavior: reducedMotion() ? 'instant' : 'smooth' });
  queueHomePosition();
  return true;
}
// 更新首页位置
function updateHomePosition() {
  homeScrollFrame = 0;
  if (!homeRoute() || $('#page-home').hidden) return;
  const current = currentHomeStage();
  const overPhotos = current < homePanels.length;

  homeDots.forEach((dot, index) => {
    const active = overPhotos && index === current;
    dot.classList.toggle('is-active', active);
    if (active) dot.setAttribute('aria-current', 'location');
    else dot.removeAttribute('aria-current');
  });
  document.body.classList.toggle('home-closing-visible', !overPhotos);
  document.body.classList.toggle('home-full-photo', overPhotos && current > 0);
  $$('[data-nav]').forEach(link => {
    if (overPhotos && link.dataset.nav === homePanels[current]?.dataset.homeTarget) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
  // Keep the indicators over the photographs, not over the closing section.
  $('.home-showcase-ui').hidden = !overPhotos;
}
function queueHomePosition() {
  if (!homeScrollFrame) homeScrollFrame = requestAnimationFrame(updateHomePosition);
}
function syncHomeRoute(view) {
  document.body.classList.toggle('home-route', homeRoute(view));
  document.documentElement.classList.toggle('home-snap', homeRoute(view));
  if (!homeRoute(view)) document.body.classList.remove('home-closing-visible');
  clearTimeout(homeUnlockTimer);
  homeState.locked = false;
  queueHomePosition();
}

/* ==========================================================================
   Account and sign-in */
const sessionKey = 'shuangfen.session';
const roleLabels = { customer: 'Customer', admin: 'Manager', frontdesk: 'Host', kitchen: 'Kitchen' };
const demoCredentials = {
  customer: { username: '13900000001', password: '123456' },
  admin: { username: 'admin@shuangfen.local', password: '123456' },
  frontdesk: { username: 'frontdesk@shuangfen.local', password: '123456' },
  kitchen: { username: 'kitchen@shuangfen.local', password: '123456' }
};
const workspaces = {
  admin: { english: 'The house', title: 'Manager', lead: 'Management preview.', tasks: [
    {title:'Accounts',text:'Customer and staff roles.'},{title:'Menu',text:'Dishes and prices.'},{title:'Settings',text:'Hours and table policies.'}] },
  frontdesk: { english: 'The floor', title: 'Front desk', lead: 'Front desk preview.', tasks: [
    {title:'Reservations',text:'Upcoming visits.'},{title:'Tables',text:'Table availability.'},{title:'Orders',text:'Dine-in orders.'}] },
  kitchen: { english: 'The pass', title: 'Kitchen', lead: 'Kitchen preview.', tasks: [
    {title:'Kitchen queue',text:'Dishes awaiting preparation.'},{title:'Availability',text:'Sold-out items.'},{title:'Service',text:'Dishes ready to serve.'}] }
};
let authMode = 'login';

function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
function currentUser() {
  const session = readStored(sessionKey, null);
  if (!session?.username || !roleLabels[session.role]) return null;
  return session;
}
function isStaff(user) { return Boolean(user) && user.role !== 'customer'; }
function clearLocalSession() { localStorage.removeItem(sessionKey); }
function saveSession(account) {
  localStorage.setItem(sessionKey, JSON.stringify({
     username: account.username, 
     name: account.name, 
     role: account.role 
    }));
}
function enterSession(account) {
  saveSession(account);
  const target = account.role === 'customer' ? (afterLogin || '#account') : '#workspace';
  afterLogin = null;
  if (location.hash === target) setRoute();
  else location.hash = target;
}
async function logout() {
  try {
    const message = await submitAuthForm(logoutUrl, {});
    if (message) throw new Error(message);
  } catch (error) {
    showRecord('Could not sign out', '<p>Check your connection and try again.</p>');
    return;
  }
  clearLocalSession();
  afterLogin = null;
  $('#login-form').reset();
  $('#register-form').reset();
  setAuthMode('login');
  if (location.hash === '#account') setRoute();
  else location.hash = '#account';
}
function showAuthError(id, message) {
  const error = $(id);
  error.hidden = !message;
  error.textContent = message || '';
}
function setAuthMode(mode) {
  authMode = mode;
  $('#auth-feedback').hidden = true;
  $('#login-form').hidden = mode !== 'login';
  $('#register-form').hidden = mode !== 'register';
  $('#show-login').setAttribute('aria-pressed', String(mode === 'login'));
  $('#show-register').setAttribute('aria-pressed', String(mode === 'register'));
}
function renderSessionChrome(user) {
  $('#account-nav').textContent = isStaff(user) ? 'Workspace' : 'Your Table';
  $('#account-nav').href = isStaff(user) ? '#workspace' : '#account';
  document.body.classList.toggle('session-staff', isStaff(user));
}
function renderAccount(user) {
  const signedInCustomer = user?.role === 'customer';
  $('#auth-guest').hidden = signedInCustomer;
  $('#auth-customer').hidden = !signedInCustomer;
  $('#page-account').setAttribute('aria-labelledby', signedInCustomer ? 'customer-title' : 'account-title');
  if (!signedInCustomer) {
    showAuthError('#login-error', '');
    showAuthError('#register-error', '');
    return;
  }
  $('#customer-title').textContent = 'Your table';
  showMyRecords();
  $('#customer-lead').textContent = `Welcome back, ${user.name}.`;
}
function renderWorkspace(user) {
  const workspace = workspaces[user.role] || workspaces.admin;
  $('#workspace-english').textContent = workspace.english;
  $('#workspace-title').textContent = workspace.title;
  $('#workspace-lead').innerHTML = workspace.lead;
  const session = document.createElement('span');
  session.className = 'muted';
  session.textContent = `${user.name} · ${roleLabels[user.role]}.`;
  $('#workspace-lead').append(document.createElement('br'), session);
  $('#workspace-tasks').innerHTML = workspace.tasks.map(task => `<article class="workspace-card"><h2>${task.title}</h2><p>${task.text}</p><span>Preview</span></article>`).join('');
}
async function restoreSessionFromServer() {
  try {
    const response = await fetch(sessionUrl, {
      credentials: 'include'
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.ok || !result.user) {
      clearLocalSession();
      return null;
    }
    saveSession(result.user);
    return result.user;
  } catch (error) {
    clearLocalSession();
    return null;
  }
}
// Flask-WTF tokens belong to the current session, which changes after sign-in.
async function submitAuthForm(endpoint, fields) {
  const tokenPage = await fetch(endpoint === logoutUrl ? loginUrl : endpoint, {cache: 'no-store'});
  if (!tokenPage.ok) throw new Error('Could not load authentication form');
  const parser = new DOMParser();
  const form = parser.parseFromString(await tokenPage.text(), 'text/html');
  const token = form.querySelector('[name="csrf_token"]')?.value;
  if (!token) throw new Error('Missing form token');
  const response = await fetch(endpoint, {
    method: 'POST',
    body: new URLSearchParams({...fields, csrf_token: token})
  });
  if (response.redirected && response.ok) return '';
  const feedback = parser.parseFromString(await response.text(), 'text/html');
  return feedback.querySelector('[data-form-error]')?.textContent.trim() ||
    'The request could not be completed. Please try again.';
}

async function loginWith(username, password) {
  if (!username.trim() || !password) return 'Enter your account and password.';

  try {
    const message = await submitAuthForm(loginUrl, {account: username.trim(), password});
    if (message) return message;
    const user = await restoreSessionFromServer();
    if (!user) return 'Could not confirm your session. Please sign in again.';
    enterSession(user);
    return '';
  } catch (error) {
    return 'Could not connect. Please try again.';
  }
}

async function registerWith(name, phone, password, passwordAgain) {
  if (!name || !phone || !password || !passwordAgain) {
    return 'Enter your name, phone number and password.';
  }

  if (name.length > 20) return 'Use 20 characters or fewer for your name.';
  if (!/^\d{11}$/.test(phone)) return 'Enter an 11-digit phone number.';
  if (password.length < 6) return 'Use at least 6 characters.';
  if (password !== passwordAgain) return 'The passwords do not match.';

  try {
    const message = await submitAuthForm(registerUrl, {name, phone_number: phone, password});
    if (message) return message;
    clearLocalSession();
    setAuthMode('login');
    $('#register-form').reset();
    $('#login-username').value = phone;
    $('#auth-feedback').textContent = 'Your account is ready. Sign in with your phone number.';
    $('#auth-feedback').hidden = false;
    $('#login-password').focus();
    return '';
  } catch (error) {
    return 'Could not connect. Please try again.';
  }
}

/* ==========================================================================
   路由*/ 
function setRoute() {
  const [page, category] = (location.hash.slice(1) || 'index').split('/');
  let view = ['index', 'navigation', 'home', 'menu', 'booking', 'delivery', 'journal', 'story', 'account', 'workspace', 'visit'].includes(page) ? page : 'index';
  const user = currentUser();
  loadCustomerRecords(user);
  if (view !== 'booking' && editingBooking) resetBooking();
  if (view === 'workspace' && !isStaff(user)) {
    view = 'account';
    history.replaceState(null, '', '#account');
  } else if (view === 'account' && isStaff(user)) {
    view = 'workspace';
    history.replaceState(null, '', '#workspace');
  }
  const story = view === 'story' ? $$('[data-story]').find(section => section.dataset.story === category) : null;
  if (view === 'story' && !story) view = 'journal';
  document.body.dataset.view = view;
  const visibleId = story ? story.id : 'page-' + (view === 'visit' ? 'home' : view);
  $$('.page').forEach(section => { section.hidden = section.id !== visibleId; });
  const navView = view === 'workspace' ? 'account' : view === 'story' ? 'journal' : view;
  $$('[data-nav]').forEach(link => link.dataset.nav === navView ? link.setAttribute('aria-current', 'page') : link.removeAttribute('aria-current'));
  const titles = { index: 'Welcome', navigation: 'House navigation', home: 'The Restaurant', visit: 'The Restaurant', menu: 'Menu', booking: 'Book a table', delivery: 'Delivery', journal: 'Journal', story: story?.querySelector('h1')?.textContent, account: 'Your table', workspace: 'Workspace' };
  document.title = titles[view] + ' · Double Portion';
  if (view !== 'menu' && state.editingCartId !== null) clearDish();

  renderSessionChrome(user);
  if (view === 'account') renderAccount(user);
  if (view === 'workspace' && user) renderWorkspace(user);
  updateMobileActions();
  syncHomeRoute(view);
  window.scrollTo({ top: 0, behavior: 'instant' });
  if (view === 'menu' && Object.hasOwn(categories, category)) selectCategory(category, true);
}

/* ==========================================================================
   Menu and bag */
let toastTimer, addTimer;

const categories = { burger:'Burgers', pizza:'Pizza', sides:'Sides', drinks:'Drinks' };

function selectCategory(category, scroll = false) {
  state.category = category;
  $$('.category-nav button').forEach(button => {
    const active = button.dataset.category === category;
    button.setAttribute('aria-pressed', String(active));
  });
  clearDish();
  if (scroll) document.getElementById('group-' + category)?.scrollIntoView({behavior: reducedMotion() ? 'instant' : 'smooth', block:'start'});
}

function renderDishes() {
  const list = $('#dish-list');
  list.replaceChildren();
  for (const [category, label] of Object.entries(categories)) {
    const section = document.createElement('section');
    section.className = 'menu-group';
    section.id = 'group-' + category;
    const heading = document.createElement('h2');
    heading.className = 'ornament-title';
    heading.textContent = label;
    section.append(heading);
    for (const dish of menu.filter(item => item.category === category)) {
      const item = document.createElement('article');
      item.className = dish.sold ? 'dish sold' : 'dish';
      item.innerHTML = `<img class="dish-img" src="${imageBase}${dish.image}" alt="${dish.name}" loading="lazy">
        <div class="dish-info"><div class="dish-line"><h3>${dish.name}</h3><span class="leader"></span><span class="dish-price">${money(dish.price)}</span></div>
        <p class="dish-description">${dish.description}</p>
        <button class="dish-select" data-dish="${dish.id}" ${dish.sold ? 'disabled' : ''}>${dish.sold ? 'Sold out' : 'Select'} ${dish.sold ? '' : '↗'}</button></div>`;
      section.append(item);
    }
    list.append(section);
  }
}

function clearDish(returnFocus = false) {
  const previousId = state.dish?.id;
  cancelLocalMotion($('.custom-content'));
  state.dish = null;
  state.editingCartId = null;
  clearTimeout(addTimer);
  $('#cancel-cart-edit').hidden = true;
  $('#custom-error').hidden = true;
  $('#customizer').hidden = true;

  $('.menu-layout').classList.remove('has-selection');
  renderDishes();

  if (returnFocus && previousId) {
    const button = $(`[data-dish="${previousId}"]`);
    button?.focus({ preventScroll: true });
    button?.scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth', block: 'center' });
  }
}

function selectDish(id, reveal = true) {
  const dish = menu.find(item => item.id === id);
  if (!dish || dish.sold) return;

  state.dish = dish; state.quantity = 1; state.editingCartId = null;
  clearTimeout(addTimer);
  $('#custom-eyebrow').textContent = 'Your selection';
  $('#cancel-cart-edit').hidden = true;
  $('#close-customizer').setAttribute('aria-label', 'Back to dishes');
  $('#add-to-cart').innerHTML = '<i data-lucide="plus"></i>Add to bag';
  $('#customizer').hidden = false; $('.menu-layout').classList.add('has-selection');
  $('#customizer').scrollTop = 0;
  $('#dish-note').value = '';
  $('#custom-title').textContent = dish.name;
  $('#custom-description').textContent = dish.description;
  $('#custom-image').hidden = !dish.image;
  if (dish.image) { $('#custom-image').src = `${imageBase}${dish.image}`; $('#custom-image').alt = dish.name; }
  const choice = (name, label, options) => `<fieldset><legend>${label}</legend><div class="choice-group">${options.map((option, index) => `<label class="choice"><input type="radio" name="${name}" value="${option.price}" data-label="${option.label}" ${index === 0 ? 'checked' : ''}><span>${option.label}<small>${option.price ? '+ ¥' + option.price : 'Included'}</small></span></label>`).join('')}</div></fieldset>`;
  const addon = (label, price) => `<label class="addon"><span><input type="checkbox" value="${price}" data-label="${label}">${label}</span><span>+ ¥${price}</span></label>`;
  let options = '';
  if (dish.category === 'pizza') {
    options += choice('size', 'Size', [{ label: '9 inch', price: 0 }, { label: '12 inch', price: 20 }]);
    options += choice('crust', 'Crust', [{ label: 'Thin crust', price: 0 }, { label: 'Thick crust', price: 4 }]);
    options += `<fieldset><legend>Extras</legend>${addon('Extra cheese', 6)}${addon('Extra mushrooms', 4)}</fieldset>`;
  } else if (dish.category === 'burger') {
    options += choice('sauce', 'Sauce', [{ label: 'House sauce', price: 0 }, { label: 'Garlic sauce', price: 0 }, { label: 'No sauce', price: 0 }]);
    options += `<fieldset><legend>Extras</legend>${addon('Extra cheddar', 4)}${dish.extraPatty ? addon('Extra patty', 12) : ''}</fieldset>`;
  } else options = '<p class="small muted" style="margin-top:18px">Choose a quantity to add to your bag.</p>';
  $('#custom-options').innerHTML = options;
  updatePrice(false); renderDishes();
  revealLocal($('.custom-content'));
  if (reveal) { $('#custom-title').focus({ preventScroll: true }); $('#customizer').scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth', block: 'start' }); }
}

function configuration() {
  const selected = $$('input:checked', $('#custom-options'));
  const unitPrice = state.dish.price + selected.reduce((sum, input) => sum + Number(input.value), 0);
  return { labels: selected.map(input => input.dataset.label), unitPrice, total: unitPrice * state.quantity };
}
function updatePrice(animate = true) {
  $('#custom-error').hidden = true;
  $('#quantity').value = state.quantity;
  $('#qty-minus').disabled = state.quantity <= 1;
  $('#qty-plus').disabled = state.quantity >= (state.editingCartId === null ? 10 : maxCartQuantity);
  $('#custom-total').textContent = money(configuration().total);
  if (animate && !reducedMotion()) {
    $('#custom-total').classList.remove('price-pop');
    requestAnimationFrame(() => $('#custom-total').classList.add('price-pop'));
  }
}

function addToCart() {
  if (!state.dish) return;
  const config = configuration();
  const signature = JSON.stringify([state.dish.id, config.labels, $('#dish-note').value.trim()]);
  const editingId = state.editingCartId;
  const existing = state.cart.find(item => item.signature === signature && item.id !== editingId);
  if ((existing?.quantity || 0) + state.quantity > maxCartQuantity) {
    $('#custom-error').textContent = `Maximum of ${maxCartQuantity} per combination.`;
    $('#custom-error').hidden = false;
    return;
  }
  const entry = { id: editingId ?? state.nextCartId++, dishId: state.dish.id, signature, name: state.dish.name, image: state.dish.image, icon: state.dish.icon, labels: config.labels, unitPrice: config.unitPrice, quantity: state.quantity, note: $('#dish-note').value.trim() };
  let savedId = entry.id;
  if (existing) {
    existing.quantity += state.quantity;
    savedId = existing.id;
    if (editingId !== null) state.cart = state.cart.filter(item => item.id !== editingId);
  } else if (editingId !== null) {
    state.cart = state.cart.map(item => item.id === editingId ? entry : item);
  } else state.cart.push(entry);
  updateCartBadge();
  if (editingId !== null) {
    clearDish();
    openCart(existing ? 'Changes saved. Matching items combined.' : 'Changes saved.');
    $(`[data-edit="${savedId}"]`)?.focus();
    return;
  }
  clearTimeout(addTimer);
  $('#add-to-cart').innerHTML = '<i data-lucide="check"></i>Added'; icons();
  addTimer = setTimeout(() => { $('#add-to-cart').innerHTML = '<i data-lucide="plus"></i>Add to bag'; icons(); }, 1300);
  $('#toast-text').textContent = `Added ${state.quantity} × ${state.dish.name}`;
  $('#toast').hidden = false; $('#toast').classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 5000);
}
function updateCartBadge() {
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  persistRecords();
  $('#cart-badge').textContent = count;
  $('#open-cart').setAttribute('aria-label', `Open bag, ${count} items`);
  updateMobileActions();
}
function updateMobileActions() {
  const page = (location.hash.slice(1) || 'index').split('/')[0];
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  const total = state.cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
  const cartVisible = page === 'menu' && count > 0;
  $('#mobile-cart-bar').hidden = !cartVisible;
  $('#mobile-cart-count').textContent = `${count} items`;
  $('#mobile-cart-total').textContent = money(total);
  document.body.classList.toggle('has-mobile-action', cartVisible);
}
async function editCartItem(id) {
  const dialog = $('#cart-dialog');
  if (!await closeDialogForAction(dialog)) return;
  const item = state.cart.find(entry => entry.id === id);
  const dish = menu.find(entry => entry.id === item?.dishId);
  if (!item || !dish) return;
  if (location.hash !== '#menu') history.pushState(null, '', '#menu');
  setRoute();
  selectCategory(dish.category);
  selectDish(dish.id, false);
  state.editingCartId = item.id;
  state.quantity = item.quantity;
  $('#dish-note').value = item.note || '';
  $$('input', $('#custom-options')).forEach(input => input.checked = item.labels.includes(input.dataset.label));
  $('#custom-eyebrow').textContent = 'Edit item';
  $('#cancel-cart-edit').hidden = false;
  $('#close-customizer').setAttribute('aria-label', 'Cancel and return to bag');
  $('#add-to-cart').innerHTML = '<i data-lucide="check"></i>Save changes';
  updatePrice(false); icons();
  $('#custom-title').focus({ preventScroll: true });
  $('#customizer').scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth', block: 'start' });
}
function cancelCartEdit() {
  const id = state.editingCartId;
  clearDish();
  openCart();
  $(`[data-edit="${id}"]`)?.focus();
}
function renderCart() {
  $('#cart-bottom').hidden = !state.cart.length;
  $('#cart-error').hidden = true;
  const ready = currentUser()?.role === 'customer' && records.visit;
  $('#place-order').disabled = !ready;
  $('#cart-visit').textContent = ready ? 'Checked in at sample table '+records.visit.table : 'Check in before ordering. You can load a sample visit in your account.';
  $('#cart-account').hidden = !!ready;
  if (!state.cart.length) {
    $('#cart-content').innerHTML = '<div class="cart-empty"><img src="'+imageBase+'pixels/burger.png" alt=""><h3>Your bag is empty</h3><p>Find something for your table.</p><button class="button primary" id="empty-browse">Explore the menu <i data-lucide="arrow-right"></i></button></div>';
  } else {
    $('#cart-content').innerHTML = state.cart.map(item => `<article class="cart-item">${item.image ? `<img src="${imageBase}${item.image}" alt="${escapeText(item.name)}">` : `<div class="dish-symbol" style="width:64px;height:67px"><i data-lucide="${item.icon}"></i></div>`}<div><h3 class="cart-item-title">${escapeText(item.name)}</h3><p>${item.labels.map(escapeText).join(', ') || 'Standard'}${item.note ? ' · '+escapeText(item.note) : ''}</p><button class="edit-item" data-edit="${item.id}" aria-label="Edit ${escapeText(item.name)}">${item.labels.length ? 'Edit options' : 'Edit quantity'}</button><div class="quantity-control"><button data-cart-change="-1" data-id="${item.id}" aria-label="Decrease ${escapeText(item.name)} quantity" ${item.quantity === 1 ? 'disabled' : ''}><i data-lucide="minus"></i></button><output>${item.quantity}</output><button data-cart-change="1" data-id="${item.id}" aria-label="Increase ${escapeText(item.name)} quantity" ${item.quantity >= maxCartQuantity ? 'disabled' : ''}><i data-lucide="plus"></i></button></div></div><div class="item-end"><span class="item-price">${money(item.unitPrice * item.quantity)}</span><button class="remove-item" data-remove="${item.id}" aria-label="Remove ${escapeText(item.name)}">Remove </button></div></article>`).join('');
  }
  $('#cart-total').textContent = money(state.cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0));
  icons();
}
function openCart(message = '') {
  if (state.editingCartId !== null) clearDish();
  renderCart(); $('#toast').hidden = true;
  $('#cart-feedback').hidden = typeof message !== 'string' || !message;
  $('#cart-feedback').textContent = typeof message === 'string' ? message : '';
  openDialog($('#cart-dialog'));
}

/* ==========================================================================
   弹窗动效*/
function dialogMotion(dialog) {
  if (!dialogMotions.has(dialog)) dialogMotions.set(dialog, { phase: 'closed', revision: 0, intent: 0, opener: null, animation: null, closePromise: null, resolveClose: null, finishClose: null });
  return dialogMotions.get(dialog);
}
function restoreDialogFocus(dialog, motion) {
  if ($$('dialog').some(item => item.open)) return;
  const fallbacks = {
    'cart-dialog': ['#open-cart'],
    'record-dialog': ['#customer-title', '[data-nav="account"]'],
    'credits-dialog': ['#open-credits']
  };
  const candidates = [motion.opener, ...(fallbacks[dialog.id] || []).map(selector => $(selector))];
  const target = candidates.find(element => {
    if (!element || element === document.body || !element.isConnected || element.disabled || dialog.contains(element)) return false;
    if (element.closest('[hidden], [inert], [aria-hidden="true"]') || !element.getClientRects().length) return false;
    return !['hidden', 'collapse'].includes(getComputedStyle(element).visibility);
  });
  target?.focus({ preventScroll: true });
}
function syncDialogScrollLock() {
  if ($$('dialog').some(dialog => dialog.open)) {
    if (dialogOverflow === null) dialogOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  } else if (dialogOverflow !== null) {
    document.body.style.overflow = dialogOverflow;
    dialogOverflow = null;
  }
}
function stopDialogAnimation(motion) {
  motion.animation?.cancel();
  motion.animation = null;
}
function settleDialogClose(motion, closed) {
  const resolve = motion.resolveClose;
  motion.closePromise = null;
  motion.resolveClose = null;
  motion.finishClose = null;
  resolve?.(closed);
}
function dialogPosition(dialog) { return dialog.classList.contains('drawer') ? 'translateX(24px)' : 'translateY(8px)'; }
function currentDialogFrame(dialog, motion, fallback) {
  if (!motion.animation) return fallback;
  const style = getComputedStyle(dialog);
  return { opacity: style.opacity, transform: style.transform };
}
function openDialog(dialog) {
  const motion = dialogMotion(dialog);
  ++motion.intent;
  if (dialog.open && motion.phase !== 'closing') return;
  const start = currentDialogFrame(dialog, motion, { opacity: 0, transform: dialogPosition(dialog) });
  const revision = ++motion.revision;
  stopDialogAnimation(motion);
  settleDialogClose(motion, false);
  if (!dialog.open) {
    motion.opener = document.activeElement;
    dialog.showModal();
  }
  syncDialogScrollLock();
  motion.phase = desktopMotion() && typeof dialog.animate === 'function' ? 'opening' : 'open';
  dialog.dataset.motionState = motion.phase;
  if (motion.phase === 'open') return;
  const animation = dialog.animate([start, { opacity: 1, transform: 'none' }], { duration: 220, easing: 'cubic-bezier(.2,.7,.2,1)' });
  motion.animation = animation;
  animation.finished.then(() => {
    if (motion.revision !== revision || !dialog.open) return;
    motion.animation = null;
    motion.phase = 'open';
    dialog.dataset.motionState = 'open';
  }, () => { });
}
function closeDialog(dialog) {
  const motion = dialogMotion(dialog);
  const intent = ++motion.intent;
  if (!dialog.open) return Promise.resolve(true);
  // Repeated dismissal shares one exit, but only its latest requested action may continue.
  if (motion.phase === 'closing') return motion.closePromise.then(closed => closed && motion.intent === intent);
  const start = currentDialogFrame(dialog, motion, { opacity: 1, transform: 'none' });
  const revision = ++motion.revision;
  stopDialogAnimation(motion);
  motion.phase = 'closing';
  dialog.dataset.motionState = 'closing';
  const pending = new Promise(resolve => { motion.resolveClose = resolve; });
  motion.closePromise = pending;
  const finish = () => {
    if (motion.revision !== revision || motion.phase !== 'closing') return;
    stopDialogAnimation(motion);
    motion.phase = 'closed';
    delete dialog.dataset.motionState;
    dialog.close();
    syncDialogScrollLock();
    if (motion.revision === revision) restoreDialogFocus(dialog, motion);
    settleDialogClose(motion, true);
  };
  motion.finishClose = finish;
  if (desktopMotion() && typeof dialog.animate === 'function') {
    motion.animation = dialog.animate([start, { opacity: 0, transform: dialogPosition(dialog) }], { duration: 160, easing: 'cubic-bezier(.4,0,1,1)' });
    motion.animation.finished.then(finish, () => { });
  } else finish();
  return pending.then(closed => closed && motion.intent === intent);
}
async function closeDialogForAction(dialog) {
  const pending = closeDialog(dialog);
  const intent = dialogMotion(dialog).intent;
  const route = location.hash;
  if (!await pending) return false;
  // Show the next view after the browser has had a rendering opportunity to release the modal.
  if (desktopMotionMedia.matches) await new Promise(resolve => requestAnimationFrame(resolve));
  return dialogMotion(dialog).intent === intent && location.hash === route && !$$('dialog').some(item => item.open);
}
async function browseFromCart() {
  const dialog = $('#cart-dialog');
  if (!await closeDialogForAction(dialog)) return;
  if (location.hash !== '#menu') history.pushState(null, '', '#menu');
  setRoute();
  $('.category-nav [aria-pressed="true"]')?.focus({ preventScroll: true });
}

/* ==========================================================================
   事件绑定与初始化*/
/* ---- 首页：滚轮 / 键盘 / 触屏 ---- */
window.addEventListener('wheel', event => {
  if (!homeRoute() || !homeShowcase || event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY) || $$('dialog').some(dialog => dialog.open)) return;
  const last = currentHomeStage() === homeStages().length-1;
  if (last && event.deltaY > 0) return;
  event.preventDefault();
  const now=performance.now();
  if (now-homeState.lastWheel>160) homeState.wheelDelta=0;
  const continuing=now-homeState.lastWheel<120;
  homeState.lastWheel=now;
  if (homeState.locked || (homeState.wheelDelta===Infinity && continuing)) return;
  if (!Number.isFinite(homeState.wheelDelta)) homeState.wheelDelta=0;
  homeState.wheelDelta += event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? innerHeight : 1);
  if (Math.abs(homeState.wheelDelta)>=18 && moveHomeStage(Math.sign(homeState.wheelDelta))) homeState.wheelDelta=Infinity;
}, { passive: false });
window.addEventListener('keydown', event => {
  if (!homeRoute() || $$('dialog').some(dialog => dialog.open)) return;
  if (document.activeElement?.closest('input, select, textarea, dialog, [contenteditable="true"]')) return;
  if (event.key === ' ' && document.activeElement?.closest('a, button')) return;
  const forward = ['ArrowDown', 'PageDown', ' '];
  const backward = ['ArrowUp', 'PageUp'];
  if (forward.includes(event.key)) {
    event.preventDefault();
    moveHomeStage(1);
  } else if (backward.includes(event.key)) {
    event.preventDefault();
    moveHomeStage(-1);
  } else if (event.key === 'Home') {
    event.preventDefault();
    window.scrollTo({ top: homeStageTop(0), behavior: reducedMotion() ? 'instant' : 'smooth' });
    lockHomeScroll();
  }
});
// A vertical swipe over a photo moves one stage, regardless of fling velocity.
let swipeStart = null;
homeShowcase.addEventListener('touchstart', event => {
  const touch = event.touches[0];
  swipeStart = event.touches.length === 1 ? { x: touch.clientX, y: touch.clientY } : null;
}, { passive: true });
homeShowcase.addEventListener('touchcancel', () => { swipeStart = null; });
homeShowcase.addEventListener('touchend', event => {
  if (!swipeStart || event.touches.length) return;
  const touch = event.changedTouches[0];
  const dy = swipeStart.y - touch.clientY;
  const dx = swipeStart.x - touch.clientX;
  swipeStart = null;
  if (Math.abs(dy) > 36 && Math.abs(dy) > Math.abs(dx)) {
    event.preventDefault();
    moveHomeStage(Math.sign(dy));
  }
}, { passive: false });
homeDots.forEach((button,index)=>button.addEventListener('click',()=>{
  window.scrollTo({top:homeStageTop(index),behavior:reducedMotion()?'instant':'smooth'});
}));
window.addEventListener('scroll', queueHomePosition, { passive: true });
window.addEventListener('resize', queueHomePosition);

/* ---- 动效偏好监听 ---- */
desktopMotionMedia.addEventListener('change', settleReducedMotion);
systemMotionMedia.addEventListener('change', settleReducedMotion);

/* ---- Menu categories and dishes ---- */
$$('.category-nav button').forEach(button => button.addEventListener('click', () => selectCategory(button.dataset.category, true)));
$('.category-nav').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const tabs = $$('.category-nav button'), current = tabs.indexOf(document.activeElement);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  selectCategory(tabs[next].dataset.category, true); tabs[next].focus();
});
$('#dish-list').addEventListener('click', event => { const button = event.target.closest('[data-dish]'); if (button) selectDish(button.dataset.dish); });
$('#close-customizer').addEventListener('click', () => state.editingCartId === null ? clearDish(true) : cancelCartEdit());
$('#cancel-cart-edit').addEventListener('click', cancelCartEdit);

/* ---- Dish options and quantity ---- */
$('#custom-options').addEventListener('change', () => updatePrice());
$('#qty-minus').addEventListener('click', () => { state.quantity = Math.max(1, state.quantity - 1); updatePrice(false); });
$('#qty-plus').addEventListener('click', () => { state.quantity = Math.min(state.editingCartId === null ? 10 : maxCartQuantity, state.quantity + 1); updatePrice(false); });
$('#add-to-cart').addEventListener('click', addToCart);

/* ---- 购物车 ---- */
$('#open-cart').addEventListener('click', openCart); $('#toast-cart').addEventListener('click', openCart);
$('#mobile-open-cart').addEventListener('click', openCart);
$('#footer-open-cart').addEventListener('click', openCart);
$('#cart-content').addEventListener('click', event => {
  const change = event.target.closest('[data-cart-change]'), remove = event.target.closest('[data-remove]'), edit = event.target.closest('[data-edit]');
  let focusTarget;
  if (edit) { editCartItem(Number(edit.dataset.edit)); return; }
  if (change) {
    const item = state.cart.find(item => item.id === Number(change.dataset.id));
    if (item) item.quantity = Math.max(1, Math.min(maxCartQuantity, item.quantity + Number(change.dataset.cartChange)));
    focusTarget = `[data-cart-change="${change.dataset.cartChange}"][data-id="${change.dataset.id}"]`;
  }
  else if (remove) {
    const index = state.cart.findIndex(item => item.id === Number(remove.dataset.remove));
    state.cart = state.cart.filter(item => item.id !== Number(remove.dataset.remove));
    const nextItem = state.cart[Math.min(index, state.cart.length - 1)];
    focusTarget = nextItem ? `[data-edit="${nextItem.id}"]` : '#empty-browse';
  }
  else if (event.target.closest('#empty-browse')) { browseFromCart(); return; }
  else return;
  $('#cart-feedback').hidden = true;
  renderCart(); updateCartBadge();
  let target = $(focusTarget);
  if (target?.disabled && change) target = $(`[data-cart-change="${-Number(change.dataset.cartChange)}"][data-id="${change.dataset.id}"]`);
  (target || $('#cart-title')).focus({ preventScroll: true });
});
/* ---- 弹窗 ---- */
$('#open-credits').addEventListener('click', () => openDialog($('#credits-dialog')));
$$('[data-open-credits]').forEach(button => button.addEventListener('click', () => openDialog($('#credits-dialog'))));
$$('[data-customer-help]').forEach(button => button.addEventListener('click', () => {
  $$('[data-help-answer]').forEach(answer => { answer.open = answer.dataset.helpAnswer === button.dataset.customerHelp; });
  openDialog($('#customer-help-dialog'));
}));
$$('dialog').forEach(dialog => {
  $('[data-close]', dialog).addEventListener('click', () => closeDialog(dialog));
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(dialog); });
  dialog.addEventListener('close', () => {
    // A queued native close event must not cancel a dialog that has since reopened.
    if (dialog.open) return;
    const motion = dialogMotion(dialog);
    ++motion.revision;
    stopDialogAnimation(motion);
    motion.phase = 'closed';
    delete dialog.dataset.motionState;
    settleDialogClose(motion, false);
    syncDialogScrollLock();
  });
  dialog.addEventListener('click', event => { if (event.target !== dialog) return; const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeDialog(dialog); });
});

/* ---- Account and sign-in ---- */
$('#show-login').addEventListener('click', () => setAuthMode('login'));
$('#show-register').addEventListener('click', () => setAuthMode('register'));

$('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const message = await loginWith(
    $('#login-username').value,
    $('#login-password').value
  );
  showAuthError('#login-error', message);
});

$('#register-form').addEventListener('submit', async event => {
  event.preventDefault();
  const message = await registerWith(
    $('#register-name').value.trim(),
    $('#register-username').value.trim(),
    $('#register-password').value,
    $('#register-password-again').value
  );
  showAuthError('#register-error', message);
});

['#login-username', '#login-password'].forEach(selector => $(selector).addEventListener('input', () => showAuthError('#login-error', '')));
['#register-name', '#register-username', '#register-password', '#register-password-again'].forEach(selector => $(selector).addEventListener('input', () => showAuthError('#register-error', '')));
$$('[data-demo]').forEach(button => button.addEventListener('click', async () => {
  const credentials = demoCredentials[button.dataset.demo];
  if (!credentials) return;
  setAuthMode('login');
  $('#login-username').value = credentials.username;
  $('#login-password').value = credentials.password;
  const message = await loginWith(credentials.username, credentials.password);
  showAuthError('#login-error', message);
}));
$('#logout-customer').addEventListener('click', logout);
$('#logout-workspace').addEventListener('click', logout);


/* ---- 路由与初始化 ---- */
$('#nav-toggle').addEventListener('click', () => {
  $('#index-close').href = location.hash || '#index';
});
window.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.body.dataset.view === 'navigation') $('#index-close').click();
});
$('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  $('#main').focus();
});
window.addEventListener('hashchange', () => {
  setRoute();
  if (document.body.dataset.view === 'navigation') $('#index-close').focus({preventScroll:true});
  else $('#main').focus({preventScroll:true});
});
async function bootstrapApp() {
  await restoreSessionFromServer();
  selectCategory('burger');
  resetBooking();
  setRoute();
  icons();
}
window.addEventListener('DOMContentLoaded', bootstrapApp, {once:true});
