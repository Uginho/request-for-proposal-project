from src.db import models

SEED_DISTRIBUTORS = [
    {
        "name": "Sysco Seattle",
        "specialty": "Broadline",
        "address": "22820 54th Ave S",
        "city": "Kent",
        "state": "WA",
        "phone": "206-622-2261",
        "website": "https://www.sysco.com",
        "email": "okols211@alumni.wfu.edu",
    },
    {
        "name": "Charlie's Produce",
        "specialty": "Produce",
        "address": "4103 2nd Ave S",
        "city": "Seattle",
        "state": "WA",
        "phone": "206-625-1412",
        "website": "https://www.charliesproduce.com",
        "email": "okols211@alumni.wfu.edu",
    },
    {
        "name": "Merlino Foods",
        "specialty": "Italian & Specialty",
        "address": "4100 4th Ave S",
        "city": "Seattle",
        "state": "WA",
        "phone": "206-723-4700",
        "website": "https://www.merlino.com",
        "email": "okols211@alumni.wfu.edu",
    },
    {
        "name": "Ocean Beauty Seafoods",
        "specialty": "Seafood",
        "address": "1100 W Ewing St",
        "city": "Seattle",
        "state": "WA",
        "phone": "206-284-6700",
        "website": "https://www.oceanbeauty.com",
        "email": "luis@workwithpathway.com",
    },
    {
        "name": "Corfini Gourmet",
        "specialty": "Meat & Proteins",
        "address": "3667 1st Ave S",
        "city": "Seattle",
        "state": "WA",
        "phone": "206-937-3141",
        "website": "https://www.corfinigourmet.com",
        "email": "luis@workwithpathway.com",
    },
    {
        "name": "Pacific Food Importers (PFI)",
        "specialty": "Mediterranean Imports",
        "address": "18620 80th Ct S",
        "city": "Kent",
        "state": "WA",
        "phone": "206-682-2740",
        "website": "https://www.pacificfoodimporters.com",
        "email": "okols211@alumni.wfu.edu",
    },
    {
        "name": "US Foods CHEF'STORE",
        "specialty": "Broadline / Cash & Carry",
        "address": "1760 4th Ave S",
        "city": "Seattle",
        "state": "WA",
        "phone": "206-682-6294",
        "website": "https://www.usfoods.com",
        "email": "okols211@alumni.wfu.edu",
    },
    {
        "name": "Duck Delivery of Washington",
        "specialty": "Produce & Dairy",
        "address": "1001 Outlet Collection Way",
        "city": "Auburn",
        "state": "WA",
        "phone": "253-549-3825",
        "website": "https://www.duckdelivery.com",
        "email": "adarsh@workwithpathway.com",
    },
    {
        "name": "S and J Food Distributors",
        "specialty": "Meat & Dry Goods",
        "address": "22 30th St NE, #102",
        "city": "Auburn",
        "state": "WA",
        "phone": "253-572-1401",
        "website": "https://sandjfoods.com",
        "email": "adarsh@workwithpathway.com",
    },
    
]


def run_distributor_finder():
    """
    Step 3 pipeline: clear and reseed the distributors table from SEED_DISTRIBUTORS.
    Idempotent — safe to run multiple times.
    Returns the full list of stored distributors.
    """
    models.clear_distributors()
    for d in SEED_DISTRIBUTORS:
        models.insert_distributor(
            name=d["name"],
            specialty=d.get("specialty"),
            address=d.get("address"),
            city=d.get("city"),
            state=d.get("state"),
            phone=d.get("phone"),
            email=d.get("email"),
            website=d.get("website"),
            notes=d.get("notes"),
        )
    return models.get_all_distributors()
