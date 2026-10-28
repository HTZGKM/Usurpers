'use strict';

/* ==========================================================================
   工具函数*/
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const money = value => `¥${value}`;
const icons = () => window.lucide?.createIcons({ attrs: { 'aria-hidden': 'true' } });
const API_BASE = 'http://127.0.0.1:5000';
/* ==========================================================================
   数据与状态*/
const menu = [
  { id: 'burger', category: 'burger', name: '芝士牛肉堡', description: '牛肉饼、车达芝士、生菜、番茄与酸黄瓜。', price: 38, image: 'wood-burger.jpg', alt: '白盘上的牛肉汉堡，配生菜和番茄', kind: 'burger' },
  { id: 'double', category: 'burger', name: '双层芝士牛肉堡', description: '双层牛肉饼，双份车达芝士。', price: 48, image: 'double-burger.jpg', alt: '木板上的双层芝士牛肉汉堡', kind: 'burger' },
  { id: 'pizza', category: 'pizza', name: '番茄芝麻菜披萨', description: '番茄、马苏里拉芝士与新鲜芝麻菜。', price: 58, image: 'pizza.jpg', alt: '一片正被取起的番茄芝麻菜披萨', kind: 'pizza' },
  { id: 'mushroom', category: 'pizza', name: '蘑菇甜椒披萨', description: '蘑菇、甜椒、芝士与番茄底酱。', price: 62, image: 'mushroom-pizza.jpg', alt: '木桌上的蘑菇甜椒披萨', kind: 'pizza' },
  { id: 'fries', category: 'sides', name: '原味薯条', description: '少许盐，配番茄酱。', price: 18, icon: 'utensils', kind: 'simple' },
  { id: 'onion', category: 'sides', name: '酥炸洋葱圈', description: '脆皮洋葱圈，配蒜香酱。', price: 22, icon: 'utensils', kind: 'simple', sold: true },
  { id: 'lemon', category: 'drinks', name: '柠檬气泡水', description: '柠檬与气泡水，加冰。', price: 16, icon: 'glass-water', kind: 'simple' },
  { id: 'tea', category: 'drinks', name: '冰红茶', description: '清爽红茶，默认少糖。', price: 14, icon: 'glass-water', kind: 'simple' }
];
const state = { category: 'burger', dish: null, quantity: 1, cart: [], editingCartId: null, selectedTable: null, area: 'all', time: '18:00', nextCartId: 1 };
const maxCartQuantity = 99;
const tableData = [
  { id: 'A1', seats: 2, location: '窗边', round: true }, { id: 'A2', seats: 2, location: '窗边', round: true }, { id: 'A3', seats: 4, location: '窗边' },
  { id: 'B1', seats: 4, location: '内侧' }, { id: 'B2', seats: 6, location: '内侧' }, { id: 'B3', seats: 6, location: '内侧' }
];

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
const homeState = { locked: false, touchStartY: 0 };
let homeScrollFrame = 0;
let homeUnlockTimer;

function homeRoute(view = (location.hash.slice(1) || 'home').split('/')[0]) {
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
  if (!homeRoute(view)) document.body.classList.remove('home-closing-visible');
  clearTimeout(homeUnlockTimer);
  homeState.locked = false;
  queueHomePosition();
}

/* ==========================================================================
   账号与登录*/
const sessionKey = 'shuangfen.session';
const roleLabels = { customer: '顾客', admin: '管理员', frontdesk: '前台', kitchen: '厨房' };
const demoCredentials = {
  customer: { username: '13900000001', password: '123456' },
  admin: { username: 'admin@shuangfen.local', password: '123456' },
  frontdesk: { username: 'frontdesk@shuangfen.local', password: '123456' },
  kitchen: { username: 'kitchen@shuangfen.local', password: '123456' }
};
const workspaces = {
  admin: {
    english: 'The house',
    title: '管理员',
    lead: '账号、菜单和店铺设置会归在这里。<br><span class="muted">还没有数据库。下面只说明以后各自做什么。</span>',
    tasks: [
      { title: '用户与角色', text: '顾客、管理员、前台、厨房。权限还不能在这里修改。' },
      { title: '菜单与价格', text: '顾客看到的仍是原型里的模拟菜单。' },
      { title: '店铺设置', text: '营业时间、桌位规则尚未开放。' }
    ]
  },
  frontdesk: {
    english: 'The floor',
    title: '前台',
    lead: '订座、桌位和到店订单会归在这里。<br><span class="muted">顾客刚提交的内容还不会传过来。</span>',
    tasks: [
      { title: '今日订座', text: '订座仍停在顾客页面的演示里。' },
      { title: '桌位', text: 'A1 到 B3 是写死的演示桌，前台还不能改状态。' },
      { title: '到店订单', text: '堂食下单还不会出现在前台。' }
    ]
  },
  kitchen: {
    english: 'The pass',
    title: '厨房',
    lead: '制作队列和售罄会归在这里。<br><span class="muted">现在还收不到顾客点的菜。</span>',
    tasks: [
      { title: '制作队列', text: '还没有从点菜传过来的订单。' },
      { title: '售罄', text: '菜单里的洋葱圈标了今日售完，厨房还不能改。' },
      { title: '出餐', text: '做好之后通知前台，这一步尚未开放。' }
    ]
  }
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
  const target = account.role === 'customer' ? '#account' : '#workspace';
  if (location.hash === target) setRoute();
  else location.hash = target;
}
async function logout() {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include'
    });
  } catch (error) {
    console.warn('退出登录时未连接到后端。', error);
  }
  clearLocalSession();
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
  $('#login-form').hidden = mode !== 'login';
  $('#register-form').hidden = mode !== 'register';
  $('#show-login').setAttribute('aria-pressed', String(mode === 'login'));
  $('#show-register').setAttribute('aria-pressed', String(mode === 'register'));
}
function renderSessionChrome(user) {
  const label = user ? user.name : '登录账号';
  $('#account-nav').textContent = label;
  $('#footer-account-link').textContent = label;
  $('#home-account-title').textContent = label;
  $('#home-account-note').textContent = user ? `已登录 · ${roleLabels[user.role]}` : '你的订单与预订。';
  $('#home-account').setAttribute('aria-label', user ? `进入${user.name}的账号` : '进入登录账号模块');
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
  $('#customer-title').textContent = user.name;
  $('#customer-lead').textContent = `${user.name}，你现在是顾客。点菜和订座可以继续用。`;
}
function renderWorkspace(user) {
  const workspace = workspaces[user.role] || workspaces.admin;
  $('#workspace-english').textContent = workspace.english;
  $('#workspace-title').textContent = workspace.title;
  $('#workspace-lead').innerHTML = workspace.lead;
  const session = document.createElement('span');
  session.className = 'muted';
  session.textContent = `${user.name} · ${roleLabels[user.role]}。登录状态由后端会话维护。`;
  $('#workspace-lead').append(document.createElement('br'), session);
  $('#workspace-tasks').innerHTML = workspace.tasks.map(task => `<article class="workspace-card"><h2>${task.title}</h2><p>${task.text}</p><span>尚未接入</span></article>`).join('');
}
async function restoreSessionFromServer() {
  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
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
// 登录校验
async function loginWith(username, password) {
  if (!username.trim() || !password) return '请填写用户名和密码。';

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.trim(),
        password
      })
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
      return result.message || '登录失败，请稍后再试。';
    }

    enterSession(result.user);
    return '';
  } catch (error) {
    return '暂时无法连接后端，请检查服务是否启动。';
  }
}

async function registerWith(name, phone, password, passwordAgain) {
  if (!name || !phone || !password || !passwordAgain) {
    return '请把姓名、手机号和密码都填上。';
  }

  if (name.length > 20) return '称呼请控制在 20 个字以内。';
  if (!/^\d{11}$/.test(phone)) return '手机号请填写 11 位数字。';
  if (password.length < 6) return '密码至少 6 位。';
  if (password !== passwordAgain) return '两次密码不一致。';

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        phone,
        password,
        role: 'customer'
      })
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
      return result.message || '注册失败，请稍后再试。';
    }

    enterSession(result.user);
    return '';
  } catch (error) {
    return '暂时无法连接后端，请检查服务是否启动。';
  }
}

/* ==========================================================================
   路由*/ 
function setRoute() {
  const [page, category] = (location.hash.slice(1) || 'home').split('/');
  let view = ['home', 'menu', 'booking', 'delivery', 'account', 'workspace', 'visit'].includes(page) ? page : 'home';
  const user = currentUser();
  if (view === 'workspace' && !isStaff(user)) {
    view = 'account';
    history.replaceState(null, '', '#account');
  } else if (view === 'account' && isStaff(user)) {
    view = 'workspace';
    history.replaceState(null, '', '#workspace');
  }
  $$('.page').forEach(section => section.hidden = section.id !== `page-${view === 'visit' ? 'home' : view}`);
  const navView = view === 'workspace' ? 'account' : view;
  $$('[data-nav]').forEach(link => link.dataset.nav === navView ? link.setAttribute('aria-current', 'page') : link.removeAttribute('aria-current'));
  const titles = { menu: '菜单', booking: '选桌订座', delivery: '外送', account: user?.role === 'customer' ? user.name : '登录账号', workspace: user ? roleLabels[user.role] : '工作台' };
  document.title = `${titles[view] || '汉堡与披萨'} · 双份`;
  if (view !== 'menu' && state.editingCartId !== null) clearDish();
  if (view === 'menu' && ['burger', 'pizza', 'sides', 'drinks'].includes(category)) selectCategory(category);
  renderSessionChrome(user);
  if (view === 'account') renderAccount(user);
  if (view === 'workspace' && user) renderWorkspace(user);
  updateMobileActions();
  syncHomeRoute(view);
  window.scrollTo({ top: 0, behavior: 'instant' });
}

/* ==========================================================================
   菜单与购物车*/   
let toastTimer, addTimer;

function selectCategory(category) {
  const changed = state.category !== category;
  state.category = category;
  $$('.category-nav button').forEach(button => {
    const active = button.dataset.category === category;
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  $('#dish-list').setAttribute('aria-labelledby', `tab-${category}`);
  clearDish();
  if (changed) revealLocal($('#dish-list'), 140, 0);
}

function renderDishes() {
  $('#dish-list').innerHTML = menu.filter(dish => dish.category === state.category).map(dish => `
    <article class="dish ${dish.id === state.dish?.id ? 'selected' : ''} ${dish.sold ? 'sold' : ''}">
      ${dish.image ? `<img class="dish-img" src="assets/images/${dish.image}" alt="${dish.alt}" width="118" height="104">` : `<div class="dish-symbol" aria-hidden="true"><i data-lucide="${dish.icon}"></i></div>`}
      <div><h3>${dish.name}</h3><p class="dish-description">${dish.description}</p><span class="dish-price">${money(dish.price)}${dish.kind !== 'simple' ? '<small>起</small>' : ''}</span>${dish.sold ? '<span class="sold-label">今日售完</span>' : ''}</div>
      <button class="dish-select" data-dish="${dish.id}" ${dish.sold ? 'disabled' : `aria-pressed="${dish.id === state.dish?.id}"`}>${dish.sold ? '已售完' : dish.id === state.dish?.id ? '已选' : dish.kind === 'simple' ? '选择' : '定制'}${!dish.sold && dish.id !== state.dish?.id ? '<i data-lucide="arrow-up-right"></i>' : ''}</button>
    </article>`).join('');
  icons();
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
  $('#customizer-prompt').hidden = false;
  $('.menu-layout').classList.remove('has-selection');
  renderDishes();
  if (previousId) revealLocal($('#customizer-prompt'));
  if (returnFocus && previousId) {
    const button = $(`[data-dish="${previousId}"]`);
    button?.focus({ preventScroll: true });
    if (matchMedia('(max-width:760px)').matches) button?.scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth', block: 'center' });
  }
}

function selectDish(id, reveal = true) {
  const dish = menu.find(item => item.id === id);
  if (!dish || dish.sold) return;
  cancelLocalMotion($('#customizer-prompt'));
  state.dish = dish; state.quantity = 1; state.editingCartId = null;
  clearTimeout(addTimer);
  $('#custom-eyebrow').textContent = '你的这一份';
  $('#cancel-cart-edit').hidden = true;
  $('#close-customizer').setAttribute('aria-label', '收起定制，返回菜品');
  $('#add-to-cart').innerHTML = '<i data-lucide="plus"></i>加入购物车';
  $('#customizer').hidden = false; $('#customizer-prompt').hidden = true; $('.menu-layout').classList.add('has-selection');
  $('#customizer').scrollTop = 0;
  $('#custom-title').textContent = dish.name;
  $('#custom-description').textContent = dish.description;
  $('#custom-image').hidden = !dish.image;
  if (dish.image) { $('#custom-image').src = `assets/images/${dish.image}`; $('#custom-image').alt = dish.alt; }
  const choice = (name, label, options) => `<fieldset><legend>${label}</legend><div class="choice-group">${options.map((option, index) => `<label class="choice"><input type="radio" name="${name}" value="${option.price}" data-label="${option.label}" ${index === 0 ? 'checked' : ''}><span>${option.label}<small>${option.price ? '+ ¥' + option.price : '原价'}</small></span></label>`).join('')}</div></fieldset>`;
  const addon = (label, price) => `<label class="addon"><span><input type="checkbox" value="${price}" data-label="${label}">${label}</span><span>+ ¥${price}</span></label>`;
  let options = '';
  if (dish.kind === 'pizza') {
    options += choice('size', '尺寸', [{ label: '9 英寸', price: 0 }, { label: '12 英寸', price: 20 }]);
    options += choice('crust', '饼底', [{ label: '经典薄底', price: 0 }, { label: '厚底', price: 4 }]);
    options += `<fieldset><legend>额外加料</legend>${addon('多加芝士', 6)}${addon('多加蘑菇', 4)}</fieldset>`;
  } else if (dish.kind === 'burger') {
    options += choice('sauce', '酱料', [{ label: '经典酱', price: 0 }, { label: '蒜香酱', price: 0 }, { label: '不加酱', price: 0 }]);
    options += `<fieldset><legend>额外加料</legend>${addon('多一片芝士', 4)}${addon('多一块牛肉饼', 12)}</fieldset>`;
  } else options = '<p class="small muted" style="margin-top:18px">按份选择数量，加入这一餐。</p>';
  $('#custom-options').innerHTML = options;
  updatePrice(false); renderDishes();
  revealLocal($('.custom-content'));
  if (reveal) { $('#custom-title').focus({ preventScroll: true }); if (matchMedia('(max-width:760px)').matches) $('#customizer').scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth', block: 'start' }); }
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
  const signature = JSON.stringify([state.dish.id, config.labels]);
  const editingId = state.editingCartId;
  const existing = state.cart.find(item => item.signature === signature && item.id !== editingId);
  if ((existing?.quantity || 0) + state.quantity > maxCartQuantity) {
    $('#custom-error').textContent = `同一口味最多 ${maxCartQuantity} 份，请减少数量后再试。`;
    $('#custom-error').hidden = false;
    return;
  }
  const entry = { id: editingId ?? state.nextCartId++, dishId: state.dish.id, signature, name: state.dish.name, image: state.dish.image, icon: state.dish.icon, labels: config.labels, unitPrice: config.unitPrice, quantity: state.quantity };
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
    openCart(existing ? '口味已更新，相同口味已合并。' : '口味已更新。');
    $(`[data-edit="${savedId}"]`)?.focus();
    return;
  }
  clearTimeout(addTimer);
  $('#add-to-cart').innerHTML = '<i data-lucide="check"></i>已加入'; icons();
  addTimer = setTimeout(() => { $('#add-to-cart').innerHTML = '<i data-lucide="plus"></i>加入购物车'; icons(); }, 1300);
  $('#toast-text').textContent = `已加入 ${state.quantity} 份${state.dish.name}`;
  $('#toast').hidden = false; $('#toast').classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 5000);
}
function updateCartBadge() {
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  $('#cart-badge').textContent = count;
  $('#open-cart').setAttribute('aria-label', `打开购物车，${count} 件`);
  updateMobileActions();
}
function updateMobileActions() {
  const page = (location.hash.slice(1) || 'home').split('/')[0];
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  const total = state.cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
  const cartVisible = page === 'menu' && count > 0;
  const bookingVisible = page === 'booking' && state.selectedTable !== null;
  $('#mobile-cart-bar').hidden = !cartVisible;
  $('#mobile-booking-bar').hidden = !bookingVisible;
  $('#mobile-cart-count').textContent = `${count} 份`;
  $('#mobile-cart-total').textContent = money(total);
  if (bookingVisible) $('#mobile-booking-summary').innerHTML = `<strong>${state.selectedTable.id} 桌 · ${$('#booking-people').value} 位</strong><span>${dateLabel()} · ${state.time}</span>`;
  document.body.classList.toggle('has-mobile-action', cartVisible || bookingVisible);
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
  $$('input', $('#custom-options')).forEach(input => input.checked = item.labels.includes(input.dataset.label));
  $('#custom-eyebrow').textContent = '修改这一份';
  $('#cancel-cart-edit').hidden = false;
  $('#close-customizer').setAttribute('aria-label', '取消修改，返回购物车');
  $('#add-to-cart').innerHTML = '<i data-lucide="check"></i>保存修改';
  updatePrice(false); icons();
  $('#custom-title').focus({ preventScroll: true });
  if (matchMedia('(max-width:760px)').matches) $('#customizer').scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth', block: 'start' });
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
  $('#dining-table').removeAttribute('aria-invalid');
  if (!state.cart.length) {
    $('#cart-content').innerHTML = '<div class="cart-empty"><i data-lucide="shopping-bag"></i><h3>这一餐，还没选好</h3><p>去菜单看看，挑一份喜欢的。</p><button class="button primary" id="empty-browse">看看菜单 <i data-lucide="arrow-right"></i></button></div>';
  } else {
    $('#cart-content').innerHTML = state.cart.map(item => `<article class="cart-item">${item.image ? `<img src="assets/images/${item.image}" alt="${item.name}">` : `<div class="dish-symbol" style="width:64px;height:67px"><i data-lucide="${item.icon}"></i></div>`}<div><h3 class="cart-item-title">${item.name}</h3><p>${item.labels.join('，') || '标准份'}</p><button class="edit-item" data-edit="${item.id}" aria-label="修改${item.name}${item.labels.length ? '口味' : '数量'}">${item.labels.length ? '修改口味' : '修改数量'}</button><div class="quantity-control"><button data-cart-change="-1" data-id="${item.id}" aria-label="减少${item.name}数量" ${item.quantity === 1 ? 'disabled' : ''}><i data-lucide="minus"></i></button><output>${item.quantity}</output><button data-cart-change="1" data-id="${item.id}" aria-label="增加${item.name}数量" ${item.quantity >= maxCartQuantity ? 'disabled' : ''}><i data-lucide="plus"></i></button></div></div><div class="item-end"><span class="item-price">${money(item.unitPrice * item.quantity)}</span><button class="remove-item" data-remove="${item.id}" aria-label="移除${item.name}">移除</button></div></article>`).join('');
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
    'booking-dialog': ['#continue-booking', '#mobile-continue-booking', '[data-nav="booking"]'],
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
  $('.category-nav [aria-selected="true"]')?.focus({ preventScroll: true });
}

/* ==========================================================================
   订座选桌*/
const localDate = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const today = new Date(); today.setHours(0, 0, 0, 0);
const tomorrow = new Date(today); tomorrow.setDate(tomorrow.getDate() + 1);
$('#booking-date').min = localDate(today); $('#booking-date').value = localDate(tomorrow);
const dateLabel = () => { const parts = $('#booking-date').value.split('-'); return parts.length === 3 ? `${Number(parts[1])} 月 ${Number(parts[2])} 日` : '请选择日期'; };
function dateValid() { return Boolean($('#booking-date').value) && $('#booking-date').value >= localDate(today); }
function renderTables() {
  cancelLocalMotion($('#selected-table'));
  state.selectedTable = null;
  const valid = dateValid(), guests = Number($('#booking-people').value);
  $('#date-error').hidden = valid;
  $('#date-error').textContent = '请选择今天或之后的日期。';
  $('#booking-date').setAttribute('aria-invalid', String(!valid));
  $('#summary-date').textContent = dateLabel();
  $('#summary-time').textContent = `${guests} 位 / ${state.time}`;
  // Availability is a deterministic fixture, never a real-time restaurant feed.
  const schedules = [['A1', 'B1'], ['A2', 'B2'], ['A3', 'B3']];
  const day = Number($('#booking-date').value.slice(-2)) || 0;
  const slot = ['17:30', '18:00', '19:30'].indexOf(state.time);
  const unavailable = schedules[(slot + day) % schedules.length];
  const fits = table => table.seats >= guests && (state.area === 'all' || table.location === state.area);
  const available = valid ? tableData.filter(table => fits(table) && !unavailable.includes(table.id)) : [];
  $('#table-availability').textContent = !valid ? '请先选择日期' : `${guests} 位 · ${state.time} · ${available.length} 张桌可选`;
  $('#table-recovery').hidden = !valid || available.length > 0;
  $('#table-help').textContent = tableData.some(fits) ? '这个时段没有符合条件的空桌，试试其他位置或时间。' : `所选位置没有可容纳 ${guests} 位的桌位，试试其他位置或调整人数。`;
  $('#show-all-tables').hidden = state.area === 'all';
  $('#try-other-time').hidden = !tableData.some(fits);
  $('#table-grid').innerHTML = tableData.map(table => {
    const reason = !valid ? '先选日期' : table.seats < guests ? `最多 ${table.seats} 位` : state.area !== 'all' && table.location !== state.area ? '其他区域' : unavailable.includes(table.id) ? '已被预订' : '可选';
    const disabled = reason !== '可选';
    return `<div class="table-space ${table.round ? 'round' : ''}"><span class="chair ${table.round ? 'left' : 'top'}" aria-hidden="true"></span><span class="chair ${table.round ? 'right' : 'bottom'}" aria-hidden="true"></span>${!table.round ? '<span class="chair left" aria-hidden="true"></span><span class="chair right" aria-hidden="true"></span>' : ''}<button class="table-button ${table.round ? 'round' : ''}" data-table="${table.id}" aria-pressed="false" ${disabled ? 'disabled' : ''} aria-label="${table.id}，${table.seats} 人桌，${table.location}，${reason}"><span>${table.id} <small>${table.seats} 人</small></span><small class="table-location">${table.location}</small><small class="table-status">${reason}</small></button></div>`;
  }).join('');
  $('#selected-table').classList.remove('is-selected');
  $('#selected-table').innerHTML = available.length ? '<i data-lucide="mouse-pointer-2"></i><p>点击地图中的空桌，<br>查看位置和座位数。</p>' : '<i data-lucide="calendar-days"></i><p>调整筛选条件，<br>再选一张合适的桌。</p>';
  $('#continue-booking').disabled = true; updateMobileActions(); icons();
}
function chooseTable(id) {
  const changed = state.selectedTable?.id !== id;
  state.selectedTable = tableData.find(table => table.id === id);
  $$('.table-button:not(:disabled)').forEach(button => {
    const active = button.dataset.table === id, table = tableData.find(table => table.id === button.dataset.table);
    button.setAttribute('aria-pressed', String(active));
    $('.table-status', button).textContent = active ? '已选择' : '可选';
    button.setAttribute('aria-label', `${table.id}，${table.seats} 人桌，${table.location}，${active ? '已选择' : '可选'}`);
  });
  const table = state.selectedTable;
  $('#selected-table').classList.add('is-selected');
  $('#selected-table').innerHTML = `<div><strong>${table.id}</strong><span class="table-detail">${table.location} · ${table.seats} 人桌</span><span class="table-party">本次 ${$('#booking-people').value} 位，整桌预订</span></div><i data-lucide="check" style="margin-left:auto"></i>`;
  $('#continue-booking').disabled = false; updateMobileActions(); icons();
  if (changed) revealLocal($('#selected-table'));
}
function bookingSummary() { return `${dateLabel()} · ${state.time} · ${$('#booking-people').value} 位<br>${state.selectedTable.id} 桌 / ${state.selectedTable.location}`; }

/* ==========================================================================
   事件绑定与初始化*/
/* ---- 首页：滚轮 / 键盘 / 触屏 ---- */
window.addEventListener('wheel', event => {
  if (!homeRoute() || !homeShowcase) return;
  if ($$('dialog').some(dialog => dialog.open) || Math.abs(event.deltaY) < 18) return;
  event.preventDefault();
  moveHomeStage(Math.sign(event.deltaY));
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
window.addEventListener('touchstart', event => {
  if (!homeRoute()) return;
  homeState.touchStartY = event.changedTouches[0]?.clientY ?? 0;
}, { passive: true });
window.addEventListener('touchend', event => {
  if (!homeRoute()) return;
  const endY = event.changedTouches[0]?.clientY ?? homeState.touchStartY;
  const deltaY = homeState.touchStartY - endY;
  if (Math.abs(deltaY) < 36) return;
  moveHomeStage(Math.sign(deltaY));
}, { passive: true });
window.addEventListener('scroll', queueHomePosition, { passive: true });
window.addEventListener('resize', queueHomePosition);

/* ---- 动效偏好监听 ---- */
desktopMotionMedia.addEventListener('change', settleReducedMotion);
systemMotionMedia.addEventListener('change', settleReducedMotion);

/* ---- 菜单分类与菜品 ---- */
$$('.category-nav button').forEach(button => button.addEventListener('click', () => selectCategory(button.dataset.category)));
$('.category-nav').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const tabs = $$('.category-nav button'), current = tabs.indexOf(document.activeElement);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  selectCategory(tabs[next].dataset.category); tabs[next].focus();
});
$('#dish-list').addEventListener('click', event => { const button = event.target.closest('[data-dish]'); if (button) selectDish(button.dataset.dish); });
$('#close-customizer').addEventListener('click', () => state.editingCartId === null ? clearDish(true) : cancelCartEdit());
$('#cancel-cart-edit').addEventListener('click', cancelCartEdit);

/* ---- 定制面板与数量 ---- */
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
$('#dining-table').addEventListener('change', () => { $('#cart-error').hidden = true; $('#dining-table').removeAttribute('aria-invalid'); });
$('#place-order').addEventListener('click', () => {
  if (!$('#dining-table').value) { $('#cart-error').hidden = false; $('#dining-table').setAttribute('aria-invalid', 'true'); $('#dining-table').focus(); return; }
  const table = $('#dining-table').value, total = state.cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
  $('#cart-content').innerHTML = `<div class="success-state"><i data-lucide="check-circle-2"></i><h3>堂食下单演示完成</h3><p>${table} 桌，共 ${money(total)}。<br>这是模拟确认，没有发送真实订单。</p><button class="button" id="empty-browse">返回菜单</button></div>`;
  $('#cart-bottom').hidden = true; state.cart = []; updateCartBadge(); icons();
  $('#empty-browse').focus();
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

/* ---- 订座选桌 ---- */
['#booking-date', '#booking-people'].forEach(selector => $(selector).addEventListener('change', renderTables));
$$('[data-time]').forEach(button => button.addEventListener('click', () => { if (state.time === button.dataset.time) return; state.time = button.dataset.time; $$('[data-time]').forEach(item => item.setAttribute('aria-pressed', String(item === button))); renderTables(); }));
function setArea(area) {
  if (state.area === area) return;
  state.area = area;
  $$('[data-area]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.area === area)));
  renderTables();
}
$$('[data-area]').forEach(button => button.addEventListener('click', () => setArea(button.dataset.area)));
$('#show-all-tables').addEventListener('click', () => { setArea('all'); $('[data-area="all"]').focus(); });
$('#try-other-time').addEventListener('click', () => {
  const times = ['17:30', '18:00', '19:30'];
  state.time = times[(times.indexOf(state.time) + 1) % times.length];
  $$('[data-time]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.time === state.time)));
  renderTables(); $(`[data-time="${state.time}"]`).focus();
});
$('#table-grid').addEventListener('click', event => { const button = event.target.closest('[data-table]'); if (button && !button.disabled) chooseTable(button.dataset.table); });
function continueBooking() {
  if (!state.selectedTable || !dateValid()) return;
  $('#contact-form').hidden = false;
  $('#contact-form').reset();
  $('#booking-dialog-content .success-state')?.remove();
  $('#confirmation-summary').hidden = false; $('#confirmation-summary').innerHTML = bookingSummary();
  ['name', 'phone'].forEach(field => { $(`#${field}-error`).hidden = true; $(`#contact-${field}`).removeAttribute('aria-invalid'); });
  openDialog($('#booking-dialog'));
}
$('#continue-booking').addEventListener('click', continueBooking);
$('#mobile-continue-booking').addEventListener('click', continueBooking);
$('#contact-form').addEventListener('submit', event => {
  event.preventDefault();
  const nameValid = $('#contact-name').value.trim().length > 0;
  const phone = $('#contact-phone').value.trim();
  const phoneValid = /^[+\d ()-]+$/.test(phone) && phone.replace(/\D/g, '').length >= 7 && phone.replace(/\D/g, '').length <= 15;
  $('#name-error').hidden = nameValid; $('#phone-error').hidden = phoneValid;
  $('#contact-name').setAttribute('aria-invalid', String(!nameValid)); $('#contact-phone').setAttribute('aria-invalid', String(!phoneValid));
  if (!nameValid || !phoneValid) { $(nameValid ? '#contact-phone' : '#contact-name').focus(); return; }
  $('#contact-form').hidden = true; $('#contact-form').reset(); $('#confirmation-summary').hidden = true;
  const success = document.createElement('div'); success.className = 'success-state';
  success.innerHTML = `<i data-lucide="check-circle-2"></i><h3>订座演示完成</h3><p>${bookingSummary()}<br>这张桌没有被真实预订。</p><button class="button primary" id="finish-booking">知道了</button>`;
  $('#booking-dialog-content').append(success); icons();
  $('#finish-booking').addEventListener('click', () => closeDialog($('#booking-dialog'))); $('#finish-booking').focus();
});
['name', 'phone'].forEach(field => $(`#contact-${field}`).addEventListener('input', () => { $(`#${field}-error`).hidden = true; $(`#contact-${field}`).removeAttribute('aria-invalid'); }));

/* ---- 账号与登录 ---- */
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
window.addEventListener('hashchange', setRoute);
async function bootstrapApp() {
  await restoreSessionFromServer();
  selectCategory('burger');
  renderTables();
  setRoute();
  icons();
}
bootstrapApp();
