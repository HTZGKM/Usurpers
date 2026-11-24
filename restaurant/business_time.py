from datetime import datetime, timedelta, timezone


RESTAURANT_TIME = timezone(timedelta(hours=8))
MEAL_SLOTS = ("11:00-14:00", "17:00-19:00", "19:00-21:00")


def current_table_window(now=None):
    local = (now or datetime.now(RESTAURANT_TIME)).astimezone(RESTAURANT_TIME)
    clock = local.strftime("%H:%M")
    slot = next((slot for slot in MEAL_SLOTS if slot[:5] <= clock < slot[6:]), None)
    return local.date().isoformat(), slot
