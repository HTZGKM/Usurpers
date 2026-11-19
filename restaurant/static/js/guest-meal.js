const dishOptionSets = {
  pizza: [
    { name: "size", title: "Size", choices: [["size-9", "9 inch", 0], ["size-12", "12 inch", 20]] },
    { name: "crust", title: "Crust", choices: [["crust-thin", "Thin crust", 0], ["crust-thick", "Thick crust", 4]] },
    { name: "extras", title: "Extras", multiple: true, choices: [["extra-cheese", "Extra cheese", 6], ["extra-mushrooms", "Extra mushrooms", 4]] },
  ],
  burger: [
    { name: "sauce", title: "Sauce", choices: [["sauce-house", "House sauce", 0], ["sauce-garlic", "Garlic sauce", 0], ["sauce-none", "No sauce", 0]] },
    { name: "extras", title: "Extras", multiple: true, choices: [["extra-cheddar", "Extra cheddar", 4], ["extra-patty", "Extra patty", 12]] },
  ],
};

function optionsForDish(dish) {
  return (dishOptionSets[dish.category] ?? []).map((group) => ({
    ...group,
    choices: group.choices.filter(([key]) => key !== "extra-patty" || dish.extraPatty),
  }));
}

function makeMealLine(dish, id, quantity, options = [], note = "") {
  const selected = optionsForDish(dish).flatMap(({ choices, multiple }) =>
    multiple
      ? choices.filter(([key]) => options.includes(key))
      : [choices.find(([key]) => options.includes(key)) ?? choices[0]],
  );
  return {
    id,
    key: dish.key,
    name: dish.name,
    quantity,
    options: selected.map(([key]) => key),
    labels: selected.map(([, label]) => label),
    note,
    unitPrice: dish.price + selected.reduce((sum, [, , price]) => sum + price, 0),
  };
}

function restoreMealBag(savedBag, menu) {
  const lines = Array.isArray(savedBag)
    ? savedBag
    : Object.entries(savedBag ?? {}).map(([key, quantity]) => ({ key, quantity }));
  return lines.flatMap((line, index) => {
    const dish = menu.get(line?.key);
    if (!dish || !Number.isInteger(line.quantity) || line.quantity < 1) return [];
    return [makeMealLine(
      dish,
      line.id ?? index + 1,
      Math.min(99, line.quantity),
      Array.isArray(line.options) ? line.options : [],
      typeof line.note === "string" ? line.note : "",
    )];
  });
}

function restoreMealOrder(savedOrder, menu, table, paid) {
  if (!savedOrder) return null;
  if (Array.isArray(savedOrder.lines)) return savedOrder;
  const lines = restoreMealBag(savedOrder, menu);
  return lines.length ? { lines, table, paid: Boolean(paid), placedAt: null } : null;
}

function mealTotal(lines) {
  return lines.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0);
}
