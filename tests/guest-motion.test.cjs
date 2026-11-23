const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname,
  '../restaurant/static/js/guest-motion.js'), 'utf8');

function mediaQuery(matches = false) {
  const listeners = new Set();
  return {
    matches,
    addEventListener(type, listener) { listeners.add(listener); },
    removeEventListener(type, listener) { listeners.delete(listener); },
    set(value) {
      this.matches = value;
      for (const listener of listeners) listener({ matches: value });
    },
    listenerCount() { return listeners.size; },
  };
}

class Photo {
  constructor(src, attributes = {}) {
    this.src = src;
    this.attributes = { alt: 'Photo description', ...attributes };
    this.style = {};
    this.listeners = new Map();
    this.parent = null;
    this.computed = { objectPosition: '50% 50%', objectFit: 'cover', opacity: '1', transform: 'none' };
  }
  cloneNode(deep) {
    assert.equal(deep, false);
    const clone = new Photo(this.src, this.attributes);
    clone.style = { ...this.style };
    return clone;
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, listener) { this.listeners.set(name, listener); }
  removeEventListener(name, listener) {
    if (this.listeners.get(name) === listener) this.listeners.delete(name);
  }
  after(node) {
    this.parent.splice(this.parent.indexOf(this) + 1, 0, node);
    node.parent = this.parent;
  }
  remove() {
    if (!this.parent) return;
    this.parent.splice(this.parent.indexOf(this), 1);
    this.parent = null;
  }
  emit(type) { this.listeners.get(type)?.({ target: this }); }
}

function harness({ matches = false, oldSrc = 'hall.webp' } = {}) {
  const timers = new Map();
  let nextTimer = 1;
  const context = {
    setTimeout(callback, delay) {
      const id = nextTimer++;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
  };
  vm.runInNewContext(source, context);
  const reducedMotion = mediaQuery(matches);
  const document = {
    children: [],
    defaultView: { getComputedStyle(photo) { return photo.computed; } },
    startViewTransition() { assert.fail('Native view transitions must not be used'); },
    querySelector(selector) {
      assert.equal(selector, '#app > :is(.cover, .ember-home) > img:not([data-guest-outgoing])');
      return this.children.find(node => node instanceof Photo &&
        !Object.hasOwn(node.attributes, 'data-guest-outgoing')) || null;
    },
    render(src) {
      for (const child of this.children) child.parent = null;
      const photo = src ? new Photo(src) : null;
      this.children = [...(photo ? [photo] : []), { type: 'navigation' }, { type: 'controls' }];
      for (const child of this.children) child.parent = this.children;
      return photo;
    },
  };
  document.render(oldSrc);
  const controller = context.createGuestPageTransition({ document, reducedMotion });
  return { controller, document, reducedMotion, timers };
}

test('commits synchronously and inserts only the outgoing photo below live controls', () => {
  const { controller, document, timers } = harness();
  const old = document.children[0];
  old.attributes.id = 'old-photo';
  old.attributes.class = 'ember-scene';
  old.computed = { objectPosition: '57% 50%', objectFit: 'cover', opacity: '0.2', transform: 'matrix(1.02, 0, 0, 1.02, 0, 0)' };
  let commits = 0;
  const copy = controller.run(() => { commits++; document.render('feast.webp'); });
  assert.equal(commits, 1);
  assert.equal(document.children[0].src, 'feast.webp');
  assert.equal(document.children[1], copy);
  assert.equal(document.children[2].type, 'navigation');
  assert.equal(document.children[3].type, 'controls');
  assert.equal(copy.src, 'hall.webp');
  assert.equal(copy.attributes['aria-hidden'], 'true');
  assert.equal(copy.attributes.alt, '');
  assert.equal(copy.attributes.id, undefined);
  assert.equal(copy.attributes.class, undefined);
  assert.deepEqual(copy.style, old.computed);
  copy.emit('animationend');
  assert.equal(copy.parent, null);
  assert.equal(timers.size, 0);
  assert.equal(document.children.length, 3);
  controller.destroy();
});

test('rapid navigation removes the old copy before committing the next route', () => {
  const { controller, document, timers } = harness();
  const first = controller.run(() => document.render('feast.webp'));
  const staleFinish = first.listeners.get('animationend');
  const staleTimeout = [...timers.values()][0].callback;
  const second = controller.run(() => {
    assert.equal(first.parent, null);
    document.render('table.webp');
  });
  assert.equal(second.src, 'feast.webp');
  assert.equal(timers.size, 1);
  staleFinish({ target: first });
  staleTimeout();
  assert.equal(second.parent, document.children);
  assert.equal(timers.size, 1);
  controller.cancel();
  assert.equal(second.parent, null);
  assert.equal(timers.size, 0);
  controller.destroy();
});

test('business updates synchronously remove motion and make their new DOM available', () => {
  const { controller, document, timers } = harness();
  const copy = controller.run(() => document.render('feast.webp'));
  let commits = 0;
  const result = controller.run(() => {
    commits++;
    assert.equal(copy.parent, null);
    document.render('updated.webp');
  }, { animate: false });
  assert.equal(result, null);
  assert.equal(commits, 1);
  assert.equal(document.children[0].src, 'updated.webp');
  assert.equal(document.children.length, 3);
  assert.equal(timers.size, 0);
  controller.destroy();
});

test('reduced motion skips copies and a preference change cleans up without rerendering', () => {
  const { controller, document, reducedMotion, timers } = harness({ matches: true });
  let commits = 0;
  assert.equal(controller.run(() => { commits++; document.render('feast.webp'); }), null);
  assert.equal(commits, 1);
  reducedMotion.set(false);
  const copy = controller.run(() => { commits++; document.render('table.webp'); });
  assert.ok(copy);
  reducedMotion.set(true);
  assert.equal(copy.parent, null);
  assert.equal(timers.size, 0);
  assert.equal(commits, 2);
  controller.destroy();
});

test('missing photos and matching sources render normally without creating copies', () => {
  for (const [oldSrc, newSrc] of [[null, 'hall.webp'], ['hall.webp', null], ['hall.webp', 'hall.webp']]) {
    const { controller, document, timers } = harness({ oldSrc });
    let commits = 0;
    assert.equal(controller.run(() => { commits++; document.render(newSrc); }), null);
    assert.equal(commits, 1);
    assert.equal(timers.size, 0);
    assert.equal(document.children.length, newSrc ? 3 : 2);
    controller.destroy();
  }
});

test('animation cancellation and a bounded fallback timer both clean up the copy', () => {
  for (const byTimer of [false, true]) {
    const { controller, document, timers } = harness();
    const copy = controller.run(() => document.render('feast.webp'));
    if (byTimer) {
      const timer = [...timers.values()][0];
      assert.ok(timer.delay >= 300 && timer.delay <= 400);
      timer.callback();
    } else copy.emit('animationcancel');
    assert.equal(copy.parent, null);
    assert.equal(copy.listeners.size, 0);
    assert.equal(timers.size, 0);
    controller.destroy();
  }
});

test('destroy is idempotent, releases listeners and keeps later updates synchronous', () => {
  const { controller, document, reducedMotion, timers } = harness();
  const copy = controller.run(() => document.render('feast.webp'));
  controller.destroy();
  controller.destroy();
  assert.equal(copy.parent, null);
  assert.equal(timers.size, 0);
  assert.equal(reducedMotion.listenerCount(), 0);
  let commits = 0;
  assert.equal(controller.run(() => { commits++; document.render('table.webp'); }), null);
  assert.equal(commits, 1);
  assert.equal(timers.size, 0);
});

test('a motion preference changed by the synchronous render prevents a new copy', () => {
  const { controller, document, reducedMotion, timers } = harness();
  let commits = 0;
  assert.equal(controller.run(() => {
    commits++;
    document.render('feast.webp');
    reducedMotion.set(true);
  }), null);
  assert.equal(commits, 1);
  assert.equal(timers.size, 0);
  controller.destroy();
});
