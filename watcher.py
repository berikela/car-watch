"""Watch myauto.ge for newly listed cars and email about them.

Searches are defined in config.toml. Listings already seen are remembered in
seen.json, so each car is only reported once.

    python watcher.py               check for new listings and email them
    python watcher.py --dry-run     print what would be emailed, change nothing
    python watcher.py --test-email  email the 3 newest matches to test the setup
"""

import argparse
import html
import json
import os
import smtplib
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config.toml"
STATE_FILE = ROOT / "seen.json"

API = "https://api2.myauto.ge/en"
MANS_URL = "https://static.my.ge/myauto/js/mans.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.myauto.ge",
    "Referer": "https://www.myauto.ge/",
}
MAX_PAGES = 10          # 30 listings per page, newest first
MAX_SEEN_PER_SEARCH = 5000

# IDs used by the myauto.ge filters.
CURRENCY = {"usd": 1, "eur": 2, "gel": 3}
FUEL = {"petrol": 2, "diesel": 3, "electric": 7, "hybrid": 6, "plug-in hybrid": 10,
        "lpg": 9, "cng": 8, "hydrogen": 12}
GEARBOX = {"manual": 1, "automatic": 2, "tiptronic": 3, "variator": 4}
DRIVE = {"front": 1, "rear": 2, "4x4": 3}
BODY = {"sedan": 1, "hatchback": 2, "universal": 3, "coupe": 4, "jeep": 5, "cabriolet": 6,
        "limousine": 15, "pickup": 29, "minivan": 30, "crossover": 66}
COLOR = {"white": 1, "beige": 2, "sky blue": 3, "yellow": 4, "green": 5, "golden": 6,
         "brown": 7, "red": 8, "orange": 9, "carnelian red": 11, "silver": 12, "grey": 13,
         "blue": 14, "black": 16, "pink": 18, "violet": 19}
LOCATION = {"tbilisi": 2, "kutaisi": 3, "batumi": 4, "poti": 7, "telavi": 8, "zugdidi": 9,
            "gori": 13, "rustavi": 15, "rustavi car market": 30, "kobuleti": 41,
            "caucasus auto market": 113, "germany": 19, "usa": 21, "japan": 22, "europe": 33}
WHEEL = {"left": 0, "right": 1}

# config key -> (API parameter, name->id table)
LIST_FILTERS = {
    "fuel": ("FuelTypes", FUEL),
    "gearbox": ("GearTypes", GEARBOX),
    "drive": ("DriveTypes", DRIVE),
    "body": ("Cats", BODY),
    "color": ("Colors", COLOR),
    "location": ("Locs", LOCATION),
}
NUMBER_FILTERS = {
    "price_from": "PriceFrom", "price_to": "PriceTo",
    "year_from": "ProdYearFrom", "year_to": "ProdYearTo",
    "mileage_from": "MileageFrom", "mileage_to": "MileageTo",
}
KNOWN_KEYS = {"name", "manufacturer", "models", "currency", "engine_from", "engine_to",
              "customs_cleared", "steering_wheel", "keyword", "extra",
              *LIST_FILTERS, *NUMBER_FILTERS}

ID_TO_NAME = {key: {v: k.title().replace("4X4", "4x4") for k, v in table.items()}
              for key, (_, table) in LIST_FILTERS.items()}


class ConfigError(Exception):
    pass


def fetch_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            last_error = error
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"myauto.ge request failed ({url}): {last_error}")


def lookup(value, table, key):
    """Turn a name from config.toml (or a raw numeric id) into a myauto.ge id."""
    if isinstance(value, int):
        return value
    try:
        return table[str(value).strip().lower()]
    except KeyError:
        options = ", ".join(sorted(table))
        raise ConfigError(f'Unknown {key} "{value}". Options: {options}') from None


def resolve_mans(search):
    """Build the Mans parameter: "<manufacturer id>.<model id>.<model id>"."""
    wanted = str(search["manufacturer"]).strip().lower()
    mans = {m["man_name"].lower(): m["man_id"] for m in fetch_json(MANS_URL)}
    if wanted not in mans:
        raise ConfigError(f'Unknown manufacturer "{search["manufacturer"]}"')
    man_id = mans[wanted]

    parts = [str(man_id)]
    models = search.get("models") or []
    if models:
        available = {m["model_name"].lower(): m["model_id"]
                     for m in fetch_json(f"{API}/getManModels", {"man_id": man_id})["data"]}
        for model in models:
            model_id = available.get(str(model).strip().lower())
            if model_id is None:
                raise ConfigError(f'Unknown model "{model}" for {search["manufacturer"]}')
            parts.append(str(model_id))
    return ".".join(parts)


def build_params(search):
    unknown = set(search) - KNOWN_KEYS
    if unknown:
        raise ConfigError(f"Unknown setting(s) in config.toml: {', '.join(sorted(unknown))}")
    if "manufacturer" not in search:
        raise ConfigError("Every [[search]] needs a manufacturer")

    params = {
        "TypeID": 0,
        "ForRent": 0,
        "Mans": resolve_mans(search),
        "CurrencyID": lookup(search.get("currency", "USD"), CURRENCY, "currency"),
        "MileageType": 1,  # km
        "SortOrder": 1,    # newest first
    }
    for key, param in NUMBER_FILTERS.items():
        if key in search:
            params[param] = int(search[key])
    for key, param in (("engine_from", "EngineVolumeFrom"), ("engine_to", "EngineVolumeTo")):
        if key in search:
            params[param] = round(float(search[key]) * 1000)  # litres -> cc
    for key, (param, table) in LIST_FILTERS.items():
        if key in search:
            values = search[key] if isinstance(search[key], list) else [search[key]]
            params[param] = ".".join(str(lookup(v, table, key)) for v in values)
    if "customs_cleared" in search:
        params["Customs"] = 1 if search["customs_cleared"] else 0
    if "steering_wheel" in search:
        params["WheelTypes"] = lookup(search["steering_wheel"], WHEEL, "steering_wheel")
    if "keyword" in search:
        params["Keyword"] = search["keyword"]
    params.update(search.get("extra", {}))
    return params


def fetch_listings(params):
    listings = []
    for page in range(1, MAX_PAGES + 1):
        data = fetch_json(f"{API}/products", {**params, "Page": page})["data"]
        listings.extend(data["items"])
        if page >= data["meta"]["last_page"]:
            break
        time.sleep(1)
    return listings


def describe(car):
    """Plain-data summary of a listing, shared by the text and HTML emails."""
    car_id = car["car_id"]
    title = f'{car.get("man_name", "")} {car.get("model_name", "")} {car.get("car_model") or ""}'
    price = f'${car["price_usd"]:,.0f}' if car.get("price_usd") else "Price negotiable"
    details = [
        f'{car["engine_volume"] / 1000:.1f} L' if car.get("engine_volume") else None,
        ID_TO_NAME["fuel"].get(car.get("fuel_type_id")),
        ID_TO_NAME["gearbox"].get(car.get("gear_type_id")),
        ID_TO_NAME["drive"].get(car.get("drive_type_id")),
        f'{car["car_run_km"]:,} km' if car.get("car_run_km") else None,
        ID_TO_NAME["location"].get(car.get("location_id")),
        "right-hand drive" if car.get("right_wheel") else None,
        "customs cleared" if car.get("customs_passed") else "customs NOT cleared",
    ]
    return {
        "title": f'{" ".join(title.split())} ({car.get("prod_year", "?")})',
        "price": price,
        "details": ", ".join(d for d in details if d),
        "url": f"https://www.myauto.ge/en/pr/{car_id}",
        "photo": (f'https://static.my.ge/myauto/photos/{car["photo"]}/thumbs/'
                  f'{car_id}_1.jpg?v={car.get("photo_ver", 0)}') if car.get("pic_number") else None,
    }


def build_email(found):
    """found: list of (search name, [car, ...])."""
    total = sum(len(cars) for _, cars in found)
    text, rows = [], []
    for name, cars in found:
        text.append(f"== {name} ==")
        rows.append(f'<h2 style="font-family:sans-serif">{html.escape(name)}</h2>')
        for car in cars:
            d = describe(car)
            text.append(f'{d["title"]} - {d["price"]}\n{d["details"]}\n{d["url"]}\n')
            photo = (f'<a href="{d["url"]}"><img src="{html.escape(d["photo"])}" width="220" '
                     f'style="border-radius:6px" alt=""></a>') if d["photo"] else ""
            rows.append(
                '<table style="font-family:sans-serif;margin-bottom:18px"><tr>'
                f'<td style="padding-right:14px;vertical-align:top">{photo}</td>'
                '<td style="vertical-align:top">'
                f'<a href="{d["url"]}" style="font-size:17px;font-weight:bold">'
                f'{html.escape(d["title"])}</a><br>'
                f'<span style="font-size:16px">{html.escape(d["price"])}</span><br>'
                f'<span style="color:#555">{html.escape(d["details"])}</span>'
                '</td></tr></table>')

    message = EmailMessage()
    if total == 1:
        d = describe(found[0][1][0])
        message["Subject"] = f'New on myauto.ge: {d["title"]} - {d["price"]}'
    else:
        message["Subject"] = f"{total} new cars on myauto.ge"
    message.set_content("\n".join(text))
    message.add_alternative("\n".join(rows), subtype="html")
    return message


def send_email(message):
    user = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASSWORD")
    if not user or not password:
        raise RuntimeError("EMAIL_USER and EMAIL_PASSWORD must be set to send email")
    message["From"] = user
    message["To"] = os.environ.get("EMAIL_TO") or user
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    with smtplib.SMTP_SSL(host, 465, timeout=30) as smtp:
        smtp.login(user, password.replace(" ", ""))
        smtp.send_message(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print new listings; do not email or save state")
    parser.add_argument("--test-email", action="store_true",
                        help="email the 3 newest matches of each search; do not save state")
    args = parser.parse_args()

    searches = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("search", [])
    if not searches:
        raise ConfigError("config.toml has no [[search]] blocks")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}

    new_state, found = {}, []
    for search in searches:
        name = search.get("name") or search.get("manufacturer", "search")
        params = build_params(search)
        # Keyed by the filters, so editing a search starts it fresh instead of
        # emailing every car that matches the new filters.
        key = urllib.parse.urlencode(sorted(params.items()))
        listings = fetch_listings(params)
        ids = [car["car_id"] for car in listings]

        if args.test_email:
            cars = listings[:3]
        elif key in state:
            seen = set(state[key])
            cars = [car for car in listings if car["car_id"] not in seen]
        else:
            cars = []  # first run of this search: remember what is already there
            print(f"[{name}] first run, remembering {len(ids)} existing listings")
        new_state[key] = sorted(set(state.get(key, [])) | set(ids))[-MAX_SEEN_PER_SEARCH:]

        print(f"[{name}] {len(listings)} listings, {len(cars)} new")
        if cars:
            found.append((name, cars))

    if found:
        message = build_email(found)
        if args.dry_run:
            print(message.get_body(("plain",)).get_content())
        else:
            send_email(message)
            print(f'Email sent: {message["Subject"]}')
    elif args.test_email:
        raise RuntimeError("No listings match the searches, so there is nothing to email")

    # Saved only after the email went out, so a failed send is retried next run.
    if not args.dry_run and not args.test_email:
        STATE_FILE.write_text(json.dumps(new_state, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (ConfigError, RuntimeError) as error:
        sys.exit(f"ERROR: {error}")
