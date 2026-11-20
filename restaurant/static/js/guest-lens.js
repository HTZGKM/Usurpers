function installNavLens(bar) {
  const lens = document.createElement("span"),
    sample = document.createElement("span");
  lens.className = "nav-lens";
  sample.className = "sample";
  lens.setAttribute("aria-hidden", "true");
  lens.append(sample);
  bar.prepend(lens);
  const photo = bar.parentElement.querySelector("img");
  sample.style.backgroundImage = 'url("' + photo.src + '")';
  let target = null,
    left = 0,
    right = 0,
    height = 0,
    alpha = 0,
    pressed = false,
    active = false,
    frame = 0,
    last = 0;
  let vLeft = 0,
    vRight = 0,
    pointer = 0,
    shine = 0.35;
  function draw(now) {
    frame = 0;
    if (!bar.isConnected || !target) return;
    const barBox = bar.getBoundingClientRect(),
      box = target.getBoundingClientRect();
    const center = box.left - barBox.left + box.width / 2;
    const w = active ? box.width * (pressed ? 0.94 : 1) : 6,
      h = active
        ? Math.min(box.height, barBox.height - 8) * (pressed ? 0.91 : 1)
        : 6;
    const l = center - w / 2,
      r = center + w / 2;
    const dt = Math.min(0.032, Math.max(0.008, (now - last) / 1000 || 0.016));
    last = now;
    if (reduce.matches) {
      left = l;
      right = r;
      height = h;
      alpha = active ? 1 : 0;
      vLeft = vRight = 0;
    } else {
      // The leading edge moves first; the trailing edge follows like a bead of liquid.
      const forward = center > (left + right) / 2;
      function step(x, v, end, rate) {
        const offset = x - end,
          k = v + rate * offset,
          e = Math.exp(-rate * dt);
        return [end + (offset + k * dt) * e, (v - rate * k * dt) * e];
      }
      [left, vLeft] = step(left, vLeft, l, forward ? 20 : 33);
      [right, vRight] = step(right, vRight, r, forward ? 33 : 20);
      const follow = 1 - Math.exp(-22 * dt);
      height += (h - height) * follow;
      alpha += ((active ? 1 : 0) - alpha) * follow;
    }
    const y = box.top - barBox.top + (box.height - height) / 2,
      width = Math.max(3, right - left);
    lens.style.transform = "translate(" + left + "px," + y + "px)";
    lens.style.width = width + "px";
    lens.style.height = Math.max(2, height) + "px";
    lens.style.opacity = alpha.toFixed(3);
    const hotspot = Math.min(
      0.93,
      Math.max(0.07, (pointer - barBox.left - left) / width),
    );
    shine = reduce.matches
      ? hotspot
      : shine + (hotspot - shine) * (1 - Math.exp(-26 * dt));
    lens.style.setProperty("--shine", shine * 100 + "%");
    if (photo.naturalWidth) {
      const imageBox = photo.getBoundingClientRect(),
        scale = Math.max(
          imageBox.width / photo.naturalWidth,
          imageBox.height / photo.naturalHeight,
        );
      const zoom = 1.18,
        iw = photo.naturalWidth * scale,
        ih = photo.naturalHeight * scale;
      const sx = barBox.left + left - imageBox.left + (iw - imageBox.width) / 2,
        sy = barBox.top + y - imageBox.top + (ih - imageBox.height) / 2;
      sample.style.backgroundSize = iw * zoom + "px " + ih * zoom + "px";
      sample.style.backgroundPosition =
        -sx * zoom -
        (width * (zoom - 1)) / 2 +
        "px " +
        (-sy * zoom - (height * (zoom - 1)) / 2) +
        "px";
    }
    if (
      !reduce.matches &&
      (Math.abs(left - l) + Math.abs(right - r) + Math.abs(height - h) > 0.06 ||
        Math.abs(alpha - (active ? 1 : 0)) > 0.002 ||
        Math.abs(shine - hotspot) > 0.003)
    )
      frame = requestAnimationFrame(draw);
    else if (!active) lens.style.opacity = "0";
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(draw);
  }
  function select(button, x) {
    if (!button) return;
    const b = button.getBoundingClientRect(),
      parent = bar.getBoundingClientRect();
    pointer = x ?? b.left + b.width / 2;
    if (!target || (!active && alpha < 0.02)) {
      left = pointer - parent.left - 3;
      right = left + 6;
      height = 6;
      vLeft = vRight = 0;
      shine = 0.5;
    }
    if (target !== button) target?.removeAttribute("data-lit");
    target = button;
    target.setAttribute("data-lit", "");
    active = true;
    schedule();
  }
  function clear() {
    active = false;
    pressed = false;
    target?.removeAttribute("data-lit");
    schedule();
  }
  const button = (e) => e.target.closest("button");
  bar.addEventListener("pointermove", (e) => {
    if (e.pointerType !== "touch") select(button(e), e.clientX);
  });
  bar.addEventListener("pointerleave", () => {
    if (!bar.querySelector(":focus-visible")) clear();
  });
  bar.addEventListener("pointerdown", (e) => {
    pressed = true;
    select(button(e), e.clientX);
  });
  bar.addEventListener("pointerup", (e) => {
    pressed = false;
    if (e.pointerType === "touch") clear();
    else schedule();
  });
  bar.addEventListener("pointercancel", clear);
  bar.addEventListener("focusin", (e) => {
    if (e.target.matches(":focus-visible")) select(button(e));
  });
  bar.addEventListener("focusout", (e) => {
    if (!bar.contains(e.relatedTarget)) clear();
  });
  new ResizeObserver(() => {
    if (active) schedule();
  }).observe(bar);
}
