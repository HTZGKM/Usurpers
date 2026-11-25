const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '../restaurant/static/js/guest.js'), 'utf8');
const readFunctions = (first, next) => source.slice(source.indexOf(first), source.indexOf(next));
const imageBase = '/static/images/atelier/';
const preview = key => imageBase + 'catalog/' + key + '.webp';
const detail = key => imageBase + 'detail/' + key + '.webp';

function createDialog() {
  const images = [];
  class DelayedImage {
    currentSrc = '';
    constructor() { images.push(this); }
    decode() {
      return new Promise((resolve, reject) => {
        this.finish = () => {
          this.currentSrc = this.src;
          resolve();
        };
        this.fail = reject;
      });
    }
  }
  const previousImage = new DelayedImage();
  previousImage.currentSrc = preview('burger');
  const frame = {
    firstElementChild: previousImage,
    replaceChildren(image) { this.firstElementChild = image; },
  };
  const fields = new Map();
  const dishSheet = {
    open: false,
    showModal() { this.open = true; },
    querySelector(selector) {
      if (selector === '.dish-image') return frame;
      if (selector === '.dish-image img') return frame.firstElementChild;
      if (!fields.has(selector)) fields.set(selector, { dataset: {} });
      return fields.get(selector);
    },
  };
  const menu = new Map([
    ['pizza', { name: 'Margherita', photo: 'pizza', category: 'pizza' }],
    ['fish', { name: 'Crisp Fish', photo: 'fish', category: 'burger' }],
  ]);
  const context = vm.createContext({
    Image: DelayedImage, imageBase, dishSheet, menu, state: { bag: [] },
    detailKey: '', detailLineId: null, detailQty: 1, customer: null,
    cats: { pizza: 'Pizzas', burger: 'Burgers' }, dishFeedback() {}, animate() {},
  });
  vm.runInContext([
    readFunctions('function asset(', 'function mount('),
    readFunctions('function showDetail(', 'function leaveDetail('),
  ].join('\n'), context);
  return { frame, images, open: key => vm.runInContext(`showDetail(${JSON.stringify(key)})`, context) };
}

test('opening a pizza immediately replaces the old dish with the current menu photo', async () => {
  const { frame, images, open } = createDialog();
  open('pizza');
  assert.notEqual(frame.firstElementChild.currentSrc, preview('burger'));
  assert.equal(frame.firstElementChild.src, preview('pizza'));
  const fullPhoto = images.find(image => image.src === detail('pizza'));
  fullPhoto.finish();
  await Promise.resolve();
  assert.equal(frame.firstElementChild, fullPhoto);
});

test('a late full-size photo cannot replace a more recently opened dish', async () => {
  const { frame, images, open } = createDialog();
  open('pizza');
  const fullPhoto = images.find(image => image.src === detail('pizza'));
  open('fish');
  fullPhoto.finish();
  await Promise.resolve();
  assert.equal(frame.firstElementChild.src, preview('fish'));
});

test('a failed full-size photo leaves the current menu photo in place', async () => {
  const { frame, images, open } = createDialog();
  open('pizza');
  images.find(image => image.src === detail('pizza')).fail(new Error('Image unavailable'));
  await Promise.resolve();
  assert.equal(frame.firstElementChild.src, preview('pizza'));
});
