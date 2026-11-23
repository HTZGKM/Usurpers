/* Fades only the previous cover photo; navigation and controls stay live. */
function createGuestPageTransition({ document, reducedMotion }) {
  const photoSelector = '#app > :is(.cover, .ember-home) > img:not([data-guest-outgoing])';
  let active = null;
  let destroyed = false;

  function cancel() {
    active?.remove();
  }

  function run(commit, { animate = true } = {}) {
    cancel();
    const previous = animate && !destroyed && !reducedMotion?.matches
      ? document.querySelector(photoSelector) : null;
    const outgoing = previous?.cloneNode(false);
    if (outgoing) {
      // A dim booking photograph must retain its appearance on a brighter page.
      const visual = document.defaultView?.getComputedStyle(previous);
      if (visual) {
        for (const property of ['objectPosition', 'objectFit', 'opacity', 'transform']) {
          outgoing.style[property] = visual[property];
        }
      }
      outgoing.removeAttribute('id');
      outgoing.removeAttribute('class');
      outgoing.setAttribute('data-guest-outgoing', '');
      outgoing.setAttribute('aria-hidden', 'true');
      outgoing.setAttribute('alt', '');
    }

    // Every route and business update exposes its new DOM before returning.
    commit();
    if (!outgoing || destroyed || reducedMotion?.matches) return null;
    const current = document.querySelector(photoSelector);
    if (!current || current.src === previous.src) return null;

    const record = {
      remove() {
        clearTimeout(record.timer);
        outgoing.removeEventListener('animationend', finish);
        outgoing.removeEventListener('animationcancel', finish);
        outgoing.remove();
        if (active === record) active = null;
      },
      timer: null,
    };
    function finish(event) {
      if (event.target === outgoing) record.remove();
    }
    active = record;
    outgoing.addEventListener('animationend', finish);
    outgoing.addEventListener('animationcancel', finish);
    // Keep the copy below the existing header, captions and floor controls.
    current.after(outgoing);
    record.timer = setTimeout(record.remove, 360);
    return outgoing;
  }

  function onMotionPreferenceChange() {
    if (reducedMotion.matches) cancel();
  }

  const modernListener = typeof reducedMotion?.addEventListener === 'function';
  if (modernListener) reducedMotion.addEventListener('change', onMotionPreferenceChange);
  else reducedMotion?.addListener?.(onMotionPreferenceChange);

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    cancel();
    if (modernListener) reducedMotion.removeEventListener('change', onMotionPreferenceChange);
    else reducedMotion?.removeListener?.(onMotionPreferenceChange);
  }

  return { run, cancel, destroy };
}
