"""Admin command-line tools.

    uv run python -m app.cli promote-admin you@example.com
    uv run python -m app.cli seed-products

Both commands are safe to run more than once.
"""

import argparse
import sys

from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Customer, Product
from app.schemas.product import ProductCreate
from app.seed_data import SEED_PRODUCTS


class CommandError(Exception):
    pass


def promote_admin(db: Session, email: str) -> Customer:
    """Give an existing, verified account the admin role."""
    customer = (
        db.query(Customer)
        .filter(func.lower(Customer.email) == email.strip().lower())
        .first()
    )
    if customer is None:
        raise CommandError(
            f"No account uses {email}. Register it on the storefront first."
        )
    if not customer.email_verified:
        raise CommandError(f"{email} has not verified its email address yet.")

    customer.role = "admin"
    customer.is_active = True
    db.commit()
    return customer


def seed_products(db: Session) -> tuple[list[str], list[str]]:
    """Add catalog products that are missing, matched by name.

    Returns (added names, skipped names). Existing products are never changed.
    """
    existing = {name.lower() for (name,) in db.query(Product.name).all()}
    added, skipped = [], []
    for data in SEED_PRODUCTS:
        if data["name"].lower() in existing:
            skipped.append(data["name"])
            continue
        # Validate with the same rules as the admin API.
        db.add(Product(**ProductCreate(**data, stock_quantity=0).model_dump()))
        added.append(data["name"])
    db.commit()
    return added, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    promote = commands.add_parser("promote-admin", help="Make an account an admin")
    promote.add_argument("email")
    commands.add_parser("seed-products", help="Load the starting product catalog")

    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        if args.command == "promote-admin":
            customer = promote_admin(db, args.email)
            print(f"{customer.email} is now an admin.")
            print("Log out and back in to see the Admin menu.")
        else:
            added, skipped = seed_products(db)
            print(f"Added {len(added)} products: {', '.join(added) or 'none'}")
            if skipped:
                print(f"Already present, left unchanged: {', '.join(skipped)}")
            if added:
                print("Stock is 0. Add stock in Admin > Inventory.")
                print("Check the wholesale prices in Admin > Products.")
    except CommandError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except ProgrammingError:
        print(
            "Error: the database tables are missing or out of date. "
            "Run `uv run python -m alembic upgrade head` first.",
            file=sys.stderr,
        )
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
