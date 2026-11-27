import json
from datetime import datetime
from pathlib import Path

from restaurant.business_time import MEAL_SLOTS, RESTAURANT_TIME
from restaurant.services import booking_service, dining_service, menu_service


SLOTS = dict(enumerate(MEAL_SLOTS, 1))
TABLE_LAYOUT = {
    1: ("A1", 16, 23), 2: ("A2", 42, 23), 3: ("A3", 67, 23),
    4: ("B1", 19, 53), 5: ("B2", 48, 53), 6: ("B3", 77, 53),
    7: ("C1", 19, 81), 8: ("C2", 48, 81),
}
CATEGORIES = {
    "burger": "Burgers", "pizza": "Pizzas", "sides": "Sides",
    "drinks": "Drinks", "other": "Other",
}


def seating_view(account):
    if not account or account["role"] not in ("customer", "frontdesk"):
        return []
    if account["role"] == "customer":
        return [
            {key: visit[key] for key in ("visit_id", "booking_id", "table_id")}
            for visit in dining_service.get_dining_sessions()
            if visit["status"] == "seated" and visit["customer_phone"] == account["username"]
        ]
    return dining_service.get_frontdesk_visits()


def restaurant_view():
    service_day = datetime.now(RESTAURANT_TIME).date().isoformat()
    with (Path(__file__).with_name("api") / "customer/catalog.json").open(encoding="utf-8") as source:
        editorial = {item["name"].casefold(): item for item in json.load(source)}
    categories = {"burgers": "burger", "pizzas": "pizza", "sides": "sides", "drinks": "drinks"}
    catalog = []
    for row in menu_service.get_all_items():
        if row["is_archived"]:
            continue
        match = editorial.get(row["dish_name"].casefold(), {})
        picture = match.get("key")
        catalog.append({
            "id": row["dish_id"],
            "key": picture or f"dish-{row['dish_id']}",
            "photo": picture,
            "name": row["dish_name"],
            "price": float(row["price"]),
            "description": row["ingredients"] or match.get("description", ""),
            "category": categories.get(row["category"], "other"),
            "sold": not row["is_available"],
        })
    tables = []
    table_ids = {}
    for row in booking_service.get_table_occupancy(service_day, 2):
        table_id = row["table_id"]
        label, x, y = TABLE_LAYOUT.get(table_id, (f"T{table_id}", None, None))
        table_ids[label] = table_id
        if x is not None:
            tables.append((label, row["capacity"], x, y))
    visible_categories = {key: label for key, label in CATEGORIES.items()
                          if key != "other" or any(dish["category"] == key for dish in catalog)}
    return dict(catalog=catalog, tables=tables, table_ids=table_ids,
                slots=SLOTS, categories=visible_categories)
