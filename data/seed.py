import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import json
from faker import Faker
from sqlalchemy import create_engine, text
from config import DB_URL

SEED = 42
fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

with open("data/distributions.json") as f:
    DIST = json.load(f)

def weighted_choice(distribution: dict) -> str:
    keys = list(distribution.keys())
    weights = list(distribution.values())
    return random.choices(keys, weights=weights, k=1)[0]

def generate(engine, n_users: int):
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE order_items, orders, users, inventory RESTART IDENTITY CASCADE"
        ))

        # Users
        users = [
            {"email": fake.unique.email(), "country": weighted_choice(DIST["users"]["countries"])}
            for _ in range(n_users)
        ]
        conn.execute(text(
            "INSERT INTO users (email, country) VALUES (:email, :country)"
        ), users)

        # Inventory
        products = [
            {
                "product_id": i,
                "name": fake.word().title(),
                "category": weighted_choice(DIST["inventory"]["categories"]),
                "stock": random.randint(0, 500),
            }
            for i in range(1, 501)
        ]
        conn.execute(text(
            "INSERT INTO inventory (product_id, name, category, stock) "
            "VALUES (:product_id, :name, :category, :stock)"
        ), products)

        # Orders and items
        n_orders = int(n_users * 2.5)
        for order_num in range(1, n_orders + 1):
            user_id = random.randint(1, n_users)
            status = weighted_choice(DIST["orders"]["status"])
            total = 0
            conn.execute(text(
                "INSERT INTO orders (id, user_id, status, total) "
                "VALUES (:id, :user_id, :status, 0)"
            ), {"id": order_num, "user_id": user_id, "status": status})

            n_items = random.randint(
                DIST["orders"]["items_per_order"]["min"],
                DIST["orders"]["items_per_order"]["max"]
            )
            items = []
            for _ in range(n_items):
                price = round(random.uniform(5, 500), 2)
                qty = random.randint(1, 5)
                total += price * qty
                items.append({
                    "order_id": order_num,
                    "product_id": random.randint(1, 500),
                    "quantity": qty,
                    "price": price,
                })
            conn.execute(text(
                "INSERT INTO order_items (order_id, product_id, quantity, price) "
                "VALUES (:order_id, :product_id, :quantity, :price)"
            ), items)
            conn.execute(text(
                "UPDATE orders SET total = :total WHERE id = :id"
            ), {"total": round(total, 2), "id": order_num})

    print(f"Seeded {n_users} users, {n_orders} orders.")


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    engine = create_engine(DB_URL)
    generate(engine, n)