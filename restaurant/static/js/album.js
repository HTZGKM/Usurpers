const filters = document.querySelectorAll('[data-filter]');
const cards = document.querySelectorAll('figure[data-category]');
filters.forEach(button => button.addEventListener('click', () => {
  filters.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  let count = 0;
  cards.forEach(card => {
    card.hidden = button.dataset.filter !== 'All' && card.dataset.category !== button.dataset.filter;
    if (!card.hidden) count++;
  });
  document.getElementById('album-count').textContent = `${count} photographs`;
}));
const dialog = document.querySelector('dialog');
document.querySelectorAll('[data-photo]').forEach(button => button.addEventListener('click', () => {
  const image = document.getElementById('large-photo');
  image.src = button.dataset.photo;
  image.alt = button.dataset.title;
  document.getElementById('photo-title').textContent = button.dataset.title;
  const source = document.getElementById('photo-source');
  source.href = button.dataset.source;
  source.textContent = `${button.dataset.credit} · View original ↗`;
  dialog.showModal();
}));
document.querySelector('.close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => {
  const rect = dialog.getBoundingClientRect();
  if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
});
