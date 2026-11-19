"""Starting product catalog, loaded with `python -m app.cli seed-products`.

Products and retail prices come from the Project-Preview site. Rice is sold in
25 kg and 50 kg bags there, so it is stored per kg here: the 25 kg bag price
divided by 25 is the retail price, and the 50 kg bag price divided by 50 is the
wholesale price from 50 kg upward.

The preview has no wholesale prices for the other products, so wholesale is
set equal to retail. Change them in Admin > Products before launch.
Stock starts at 0; add real stock in Admin > Inventory so it is recorded.
"""

SEED_PRODUCTS: list[dict] = [
    {
        "name": "Regular Rice",
        "category": "Rice",
        "description": "Everyday white rice for daily meals.",
        "unit": "kg",
        "retail_price": 60,  # 1500 per 25 kg bag
        "wholesale_price": 59,  # 2950 per 50 kg bag
        "min_wholesale_quantity": 50,
        "image_url": "images/regular-rice.jpg",
    },
    {
        "name": "Sona Masuri Rice",
        "category": "Rice",
        "description": "Light, aromatic medium-grain rice from Andhra fields.",
        "unit": "kg",
        "retail_price": 80,  # 2000 per 25 kg bag
        "wholesale_price": 79,  # 3950 per 50 kg bag
        "min_wholesale_quantity": 50,
        "image_url": "images/sona-masoori-rice.jpg",
    },
    {
        "name": "Brown Rice",
        "category": "Rice",
        "description": "Whole-grain rice with the bran kept on.",
        "unit": "kg",
        "retail_price": 100,  # 2500 per 25 kg bag
        "wholesale_price": 98,  # 4900 per 50 kg bag
        "min_wholesale_quantity": 50,
        "image_url": "images/brown-rice.jpg",
    },
    {
        "name": "Toor Dal",
        "category": "Pulses",
        "description": "Cleaned and unpolished toor dal.",
        "unit": "kg",
        "retail_price": 150,
        "wholesale_price": 150,
        "min_wholesale_quantity": 25,
        "image_url": "images/toor-dal.jpg",
    },
    {
        "name": "Whole Green Gram",
        "category": "Pulses",
        "description": "Cleaned whole green gram.",
        "unit": "kg",
        "retail_price": 110,
        "wholesale_price": 110,
        "min_wholesale_quantity": 25,
        "image_url": "images/whole-green-gram.jpg",
    },
    {
        "name": "Red Chilli Powder",
        "category": "Spices",
        "description": "Ground red chilli powder.",
        "unit": "kg",
        "retail_price": 220,
        "wholesale_price": 220,
        "min_wholesale_quantity": 10,
        "image_url": "images/red-chilli-powder.jpg",
    },
    {
        "name": "Pure Ghee",
        "category": "Ghee",
        "description": "Golden ghee for everyday cooking.",
        "unit": "kg",
        "retail_price": 700,
        "wholesale_price": 700,
        "min_wholesale_quantity": 10,
        "image_url": "images/ghee.jpg",
    },
    {
        "name": "Natural Jaggery",
        "category": "Sweeteners",
        "description": "Traditional cane jaggery.",
        "unit": "kg",
        "retail_price": 80,
        "wholesale_price": 80,
        "min_wholesale_quantity": 25,
        "image_url": "images/jaggery.jpg",
    },
]
