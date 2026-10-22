"""Fixed reference data the generator draws from: places, the catalog's shape, species and seasonality."""

from dataclasses import dataclass, field

ET, CT, MT, AZ, PT = 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Phoenix', 'America/Los_Angeles'
DETROIT, INDY, BOISE = 'America/Detroit', 'America/Indiana/Indianapolis', 'America/Boise'

REGIONS = [
    ('NE', 'Northeast'),
    ('SE', 'Southeast'),
    ('MW', 'Midwest'),
    ('SC', 'South Central'),
    ('MT', 'Mountain'),
    ('PA', 'Pacific'),
]


@dataclass(frozen=True)
class City:
    name: str
    state: str
    region: str
    time_zone: str
    weight: float  # Roughly the metro population in millions; decides how many stores a city gets.
    area_codes: tuple
    zip3: str


def _cities(region, rows):
    return [City(name, state, region, tz, weight, tuple(codes.split()), zip3)
            for name, state, tz, weight, codes, zip3 in rows]


CITIES = (
    _cities('NE', [
        ('New York', 'NY', ET, 8.3, '212 718 917 646', '100'),
        ('Buffalo', 'NY', ET, 0.9, '716', '142'),
        ('Rochester', 'NY', ET, 0.7, '585', '146'),
        ('Albany', 'NY', ET, 0.6, '518', '122'),
        ('Philadelphia', 'PA', ET, 1.6, '215 267', '191'),
        ('Pittsburgh', 'PA', ET, 1.0, '412', '152'),
        ('Allentown', 'PA', ET, 0.4, '610', '181'),
        ('Boston', 'MA', ET, 1.9, '617 857', '021'),
        ('Worcester', 'MA', ET, 0.5, '508', '016'),
        ('Hartford', 'CT', ET, 0.6, '860', '061'),
        ('Stamford', 'CT', ET, 0.4, '203', '069'),
        ('Providence', 'RI', ET, 0.6, '401', '029'),
        ('Portland', 'ME', ET, 0.3, '207', '041'),
        ('Manchester', 'NH', ET, 0.3, '603', '031'),
        ('Burlington', 'VT', ET, 0.2, '802', '054'),
        ('Newark', 'NJ', ET, 0.9, '973', '071'),
        ('Trenton', 'NJ', ET, 0.4, '609', '086'),
        ('Baltimore', 'MD', ET, 1.1, '410 443', '212'),
        ('Bethesda', 'MD', ET, 0.5, '301', '208'),
        ('Wilmington', 'DE', ET, 0.3, '302', '198'),
    ])
    + _cities('SE', [
        ('Miami', 'FL', ET, 2.0, '305 786', '331'),
        ('Orlando', 'FL', ET, 1.3, '407', '328'),
        ('Tampa', 'FL', ET, 1.4, '813', '336'),
        ('Jacksonville', 'FL', ET, 1.0, '904', '322'),
        ('Fort Lauderdale', 'FL', ET, 0.9, '954', '333'),
        ('Tallahassee', 'FL', ET, 0.3, '850', '323'),
        ('Atlanta', 'GA', ET, 2.2, '404 678 770', '303'),
        ('Savannah', 'GA', ET, 0.3, '912', '314'),
        ('Charlotte', 'NC', ET, 1.3, '704 980', '282'),
        ('Raleigh', 'NC', ET, 1.0, '919 984', '276'),
        ('Greensboro', 'NC', ET, 0.5, '336', '274'),
        ('Charleston', 'SC', ET, 0.5, '843', '294'),
        ('Columbia', 'SC', ET, 0.5, '803', '292'),
        ('Richmond', 'VA', ET, 0.8, '804', '232'),
        ('Virginia Beach', 'VA', ET, 0.9, '757', '234'),
        ('Arlington', 'VA', ET, 0.7, '703 571', '222'),
        ('Nashville', 'TN', CT, 1.2, '615 629', '372'),
        ('Memphis', 'TN', CT, 0.8, '901', '381'),
        ('Knoxville', 'TN', ET, 0.5, '865', '379'),
        ('Birmingham', 'AL', CT, 0.6, '205', '352'),
        ('Huntsville', 'AL', CT, 0.4, '256', '358'),
    ])
    + _cities('MW', [
        ('Chicago', 'IL', CT, 3.5, '312 773 872', '606'),
        ('Naperville', 'IL', CT, 0.6, '630', '605'),
        ('Springfield', 'IL', CT, 0.2, '217', '627'),
        ('Columbus', 'OH', ET, 1.4, '614', '432'),
        ('Cleveland', 'OH', ET, 1.0, '216', '441'),
        ('Cincinnati', 'OH', ET, 1.0, '513', '452'),
        ('Detroit', 'MI', DETROIT, 1.5, '313', '482'),
        ('Grand Rapids', 'MI', DETROIT, 0.6, '616', '495'),
        ('Ann Arbor', 'MI', DETROIT, 0.4, '734', '481'),
        ('Indianapolis', 'IN', INDY, 1.2, '317', '462'),
        ('Fort Wayne', 'IN', INDY, 0.4, '260', '468'),
        ('Milwaukee', 'WI', CT, 0.9, '414', '532'),
        ('Madison', 'WI', CT, 0.5, '608', '537'),
        ('Minneapolis', 'MN', CT, 1.4, '612 763 952', '554'),
        ('St. Paul', 'MN', CT, 0.6, '651', '551'),
        ('Kansas City', 'MO', CT, 1.0, '816', '641'),
        ('St. Louis', 'MO', CT, 1.1, '314 636', '631'),
        ('Des Moines', 'IA', CT, 0.5, '515', '503'),
        ('Omaha', 'NE', CT, 0.6, '402', '681'),
        ('Wichita', 'KS', CT, 0.5, '316', '672'),
    ])
    + _cities('SC', [
        ('Houston', 'TX', CT, 2.8, '713 281 832', '770'),
        ('Dallas', 'TX', CT, 2.4, '214 469 972', '752'),
        ('Austin', 'TX', CT, 1.5, '512 737', '787'),
        ('San Antonio', 'TX', CT, 1.5, '210', '782'),
        ('Fort Worth', 'TX', CT, 1.0, '817', '761'),
        ('El Paso', 'TX', MT, 0.7, '915', '799'),
        ('Plano', 'TX', CT, 0.6, '972', '750'),
        ('Oklahoma City', 'OK', CT, 0.8, '405', '731'),
        ('Tulsa', 'OK', CT, 0.6, '918', '741'),
        ('New Orleans', 'LA', CT, 0.7, '504', '701'),
        ('Baton Rouge', 'LA', CT, 0.5, '225', '708'),
        ('Little Rock', 'AR', CT, 0.4, '501', '722'),
    ])
    + _cities('MT', [
        ('Denver', 'CO', MT, 1.6, '303 720', '802'),
        ('Colorado Springs', 'CO', MT, 0.7, '719', '809'),
        ('Fort Collins', 'CO', MT, 0.4, '970', '805'),
        ('Phoenix', 'AZ', AZ, 2.0, '602 480 623', '850'),
        ('Tucson', 'AZ', AZ, 0.8, '520', '857'),
        ('Mesa', 'AZ', AZ, 0.6, '480', '852'),
        ('Salt Lake City', 'UT', MT, 0.9, '801 385', '841'),
        ('Provo', 'UT', MT, 0.4, '801', '846'),
        ('Las Vegas', 'NV', PT, 1.5, '702 725', '891'),
        ('Reno', 'NV', PT, 0.5, '775', '895'),
        ('Albuquerque', 'NM', MT, 0.7, '505', '871'),
        ('Boise', 'ID', BOISE, 0.6, '208', '837'),
        ("Coeur d'Alene", 'ID', PT, 0.2, '208', '838'),
    ])
    + _cities('PA', [
        ('Los Angeles', 'CA', PT, 3.9, '213 310 323 818', '900'),
        ('San Diego', 'CA', PT, 1.4, '619 858', '921'),
        ('San Jose', 'CA', PT, 1.0, '408 669', '951'),
        ('San Francisco', 'CA', PT, 0.9, '415 628', '941'),
        ('Sacramento', 'CA', PT, 0.9, '916', '958'),
        ('Fresno', 'CA', PT, 0.6, '559', '937'),
        ('Oakland', 'CA', PT, 0.6, '510', '946'),
        ('Irvine', 'CA', PT, 0.5, '949', '926'),
        ('Riverside', 'CA', PT, 0.6, '951', '925'),
        ('Seattle', 'WA', PT, 1.5, '206', '981'),
        ('Tacoma', 'WA', PT, 0.5, '253', '984'),
        ('Spokane', 'WA', PT, 0.5, '509', '992'),
        ('Bellingham', 'WA', PT, 0.2, '360', '982'),
        ('Vancouver', 'WA', PT, 0.4, '360', '986'),
        ('Portland', 'OR', PT, 1.2, '503 971', '972'),
        ('Eugene', 'OR', PT, 0.4, '541', '974'),
        ('Salem', 'OR', PT, 0.3, '503', '973'),
        ('Bend', 'OR', PT, 0.2, '541', '977'),
    ])
)

# The center of each city above, (latitude, longitude), for the demo sign-in map.
CITY_COORDINATES = {
    ('Albany', 'NY'): (42.65, -73.76), ('Albuquerque', 'NM'): (35.08, -106.65), ('Allentown', 'PA'): (40.60, -75.49),
    ('Ann Arbor', 'MI'): (42.28, -83.74), ('Arlington', 'VA'): (38.88, -77.10), ('Atlanta', 'GA'): (33.75, -84.39),
    ('Austin', 'TX'): (30.27, -97.74), ('Baltimore', 'MD'): (39.29, -76.61), ('Baton Rouge', 'LA'): (30.45, -91.19),
    ('Bellingham', 'WA'): (48.75, -122.48), ('Bend', 'OR'): (44.06, -121.32), ('Bethesda', 'MD'): (38.98, -77.10),
    ('Birmingham', 'AL'): (33.52, -86.80), ('Boise', 'ID'): (43.62, -116.20), ('Boston', 'MA'): (42.36, -71.06),
    ('Buffalo', 'NY'): (42.89, -78.88), ('Charleston', 'SC'): (32.78, -79.93), ('Charlotte', 'NC'): (35.23, -80.84),
    ('Chicago', 'IL'): (41.88, -87.63), ('Cincinnati', 'OH'): (39.10, -84.51), ('Cleveland', 'OH'): (41.50, -81.69),
    ("Coeur d'Alene", 'ID'): (47.68, -116.78), ('Colorado Springs', 'CO'): (38.83, -104.82),
    ('Columbia', 'SC'): (34.00, -81.03), ('Columbus', 'OH'): (39.96, -83.00), ('Dallas', 'TX'): (32.78, -96.80),
    ('Denver', 'CO'): (39.74, -104.99), ('Des Moines', 'IA'): (41.59, -93.62), ('Detroit', 'MI'): (42.33, -83.05),
    ('El Paso', 'TX'): (31.76, -106.49), ('Eugene', 'OR'): (44.05, -123.09), ('Fort Collins', 'CO'): (40.59, -105.08),
    ('Fort Lauderdale', 'FL'): (26.12, -80.14), ('Fort Wayne', 'IN'): (41.08, -85.14),
    ('Fort Worth', 'TX'): (32.76, -97.33), ('Fresno', 'CA'): (36.74, -119.79), ('Grand Rapids', 'MI'): (42.96, -85.67),
    ('Greensboro', 'NC'): (36.07, -79.79), ('Hartford', 'CT'): (41.76, -72.67), ('Houston', 'TX'): (29.76, -95.37),
    ('Huntsville', 'AL'): (34.73, -86.59), ('Indianapolis', 'IN'): (39.77, -86.16), ('Irvine', 'CA'): (33.68, -117.83),
    ('Jacksonville', 'FL'): (30.33, -81.66), ('Kansas City', 'MO'): (39.10, -94.58), ('Knoxville', 'TN'): (35.96, -83.92),
    ('Las Vegas', 'NV'): (36.17, -115.14), ('Little Rock', 'AR'): (34.75, -92.29), ('Los Angeles', 'CA'): (34.05, -118.24),
    ('Madison', 'WI'): (43.07, -89.40), ('Memphis', 'TN'): (35.15, -90.05), ('Mesa', 'AZ'): (33.42, -111.83),
    ('Miami', 'FL'): (25.76, -80.19), ('Milwaukee', 'WI'): (43.04, -87.91), ('Minneapolis', 'MN'): (44.98, -93.27),
    ('Naperville', 'IL'): (41.75, -88.15), ('Nashville', 'TN'): (36.16, -86.78), ('New Orleans', 'LA'): (29.95, -90.07),
    ('New York', 'NY'): (40.71, -74.01), ('Newark', 'NJ'): (40.74, -74.17), ('Oakland', 'CA'): (37.80, -122.27),
    ('Oklahoma City', 'OK'): (35.47, -97.52), ('Omaha', 'NE'): (41.26, -95.93), ('Orlando', 'FL'): (28.54, -81.38),
    ('Philadelphia', 'PA'): (39.95, -75.17), ('Phoenix', 'AZ'): (33.45, -112.07), ('Pittsburgh', 'PA'): (40.44, -79.99),
    ('Plano', 'TX'): (33.02, -96.70), ('Portland', 'OR'): (45.52, -122.68), ('Providence', 'RI'): (41.82, -71.41),
    ('Provo', 'UT'): (40.23, -111.66), ('Raleigh', 'NC'): (35.78, -78.64), ('Reno', 'NV'): (39.53, -119.81),
    ('Richmond', 'VA'): (37.54, -77.44), ('Riverside', 'CA'): (33.95, -117.40), ('Rochester', 'NY'): (43.16, -77.61),
    ('Sacramento', 'CA'): (38.58, -121.49), ('Salem', 'OR'): (44.94, -123.04), ('Salt Lake City', 'UT'): (40.76, -111.89),
    ('San Antonio', 'TX'): (29.42, -98.49), ('San Diego', 'CA'): (32.72, -117.16), ('San Francisco', 'CA'): (37.77, -122.42),
    ('San Jose', 'CA'): (37.34, -121.89), ('Seattle', 'WA'): (47.61, -122.33), ('Spokane', 'WA'): (47.66, -117.43),
    ('St. Louis', 'MO'): (38.63, -90.20), ('St. Paul', 'MN'): (44.95, -93.09), ('Stamford', 'CT'): (41.05, -73.54),
    ('Tacoma', 'WA'): (47.25, -122.44), ('Tampa', 'FL'): (27.95, -82.46), ('Tucson', 'AZ'): (32.22, -110.97),
    ('Tulsa', 'OK'): (36.15, -95.99), ('Vancouver', 'WA'): (45.64, -122.66), ('Virginia Beach', 'VA'): (36.85, -75.98),
    ('Wichita', 'KS'): (37.69, -97.34), ('Worcester', 'MA'): (42.26, -71.80),
    ('Burlington', 'VT'): (44.48, -73.21), ('Manchester', 'NH'): (42.99, -71.46), ('Portland', 'ME'): (43.66, -70.26),
    ('Savannah', 'GA'): (32.08, -81.09), ('Springfield', 'IL'): (39.78, -89.65), ('Tallahassee', 'FL'): (30.44, -84.28),
    ('Trenton', 'NJ'): (40.22, -74.76), ('Wilmington', 'DE'): (39.74, -75.55),
}

# Critter Corner, the chain Pets Central bought, only had stores in these states.
ACQUIRED_CHAIN_STATES = {'WA', 'OR', 'ID'}
STORE_NAME_SUFFIXES = ['North', 'South', 'East', 'West', 'Downtown', 'Midtown', 'Lakeside', 'Hillcrest', 'Riverside',
                       'Uptown', 'Crossroads', 'Commons', 'Village', 'Park']


@dataclass(frozen=True)
class CategorySpec:
    name: str
    sales_share: float       # Share of the department's sale lines.
    assortment_share: float  # Share of the department's products.
    price_range: tuple       # List price range in dollars for a new product.
    margin_range: tuple      # Gross margin range: cost = price * (1 - margin).
    quantity: str            # How many units a line usually has; see QUANTITY_DISTRIBUTIONS.
    nouns: tuple = ()
    sizes: tuple = ('',)
    live: bool = False       # Products are species, and each animal is tracked individually.


@dataclass(frozen=True)
class DepartmentSpec:
    code: str
    name: str
    owner_share: float       # Share of customers whose main pet is this kind.
    categories: list = field(default_factory=list)


FOOD_SIZES_DOG = ('4 lb', '5 lb', '12 lb', '15 lb', '24 lb', '30 lb', '35 lb', '40 lb')
FOOD_SIZES_CAT = ('3 lb', '3.5 lb', '7 lb', '11 lb', '14 lb', '16 lb')
CAN_SIZES = ('3 oz', '5.5 oz', '12.5 oz', '13 oz', '12 x 3 oz', '24 x 3 oz')
TOY_SIZES = ('Small', 'Medium', 'Large', 'XL')

DEPARTMENTS = [
    DepartmentSpec('DOG', 'Dogs', 0.42, [
        CategorySpec('Dry Food', .28, .14, (14, 90), (.28, .38), 'single',
                     ('Adult Recipe', 'Puppy Recipe', 'Senior Formula', 'Grain-Free Salmon', 'Chicken & Rice',
                      'Lamb & Brown Rice', 'Large Breed', 'Small Breed', 'Healthy Weight', 'Sensitive Stomach',
                      'High Protein Bison', 'Limited Ingredient Duck'), FOOD_SIZES_DOG),
        CategorySpec('Wet Food', .12, .14, (1.5, 5), (.32, .42), 'cans',
                     ('Beef Stew', 'Chicken Dinner', 'Turkey & Rice Loaf', 'Lamb Casserole', 'Salmon Pate',
                      'Puppy Chicken Pate', 'Senior Chicken Stew', 'Hearty Beef Chunks'), CAN_SIZES),
        CategorySpec('Treats & Chews', .15, .16, (4, 25), (.40, .55), 'few',
                     ('Dental Chews', 'Jerky Strips', 'Training Bites', 'Bully Sticks', 'Peanut Butter Biscuits',
                      'Chicken Chips', 'Antler Chew', 'Freeze-Dried Liver'), ('4 oz', '6 oz', '12 oz', '24 ct')),
        CategorySpec('Toys', .10, .16, (5, 30), (.45, .60), 'few',
                     ('Rope Tug', 'Squeaky Plush Fox', 'Rubber Chew Ball', 'Treat Puzzle', 'Fetch Launcher',
                      'Flying Disc', 'Crinkle Duck', 'Durable Chew Bone'), TOY_SIZES),
        CategorySpec('Beds & Crates', .05, .08, (30, 200), (.38, .50), 'single',
                     ('Orthopedic Bed', 'Bolster Bed', 'Wire Crate', 'Plastic Kennel', 'Cooling Mat',
                      'Donut Cuddler'), TOY_SIZES),
        CategorySpec('Collars, Leashes & Harnesses', .08, .12, (10, 50), (.45, .60), 'single',
                     ('Nylon Collar', 'Leather Collar', 'No-Pull Harness', 'Retractable Leash', '6 ft Leash',
                      'Reflective Harness'), TOY_SIZES),
        CategorySpec('Grooming', .06, .08, (6, 40), (.40, .55), 'single',
                     ('Oatmeal Shampoo', 'Slicker Brush', 'Nail Clippers', 'Deshedding Tool', 'Ear Cleaner',
                      'Detangling Spray'), ('',)),
        CategorySpec('Health & Wellness', .16, .12, (9, 80), (.30, .45), 'single',
                     ('Flea & Tick Topical', 'Flea & Tick Collar', 'Hip & Joint Chews', 'Probiotic Powder',
                      'Calming Chews', 'Fish Oil Supplement', 'Dewormer'),
                     ('Small Dog', 'Medium Dog', 'Large Dog', '60 ct', '120 ct')),
    ]),
    DepartmentSpec('CAT', 'Cats', 0.33, [
        CategorySpec('Dry Food', .22, .13, (9, 60), (.28, .38), 'single',
                     ('Indoor Formula', 'Kitten Recipe', 'Senior Formula', 'Grain-Free Chicken',
                      'Salmon & Rice', 'Hairball Control', 'Urinary Health', 'Healthy Weight'), FOOD_SIZES_CAT),
        CategorySpec('Wet Food', .18, .18, (1, 4), (.32, .42), 'cans',
                     ('Tuna Pate', 'Chicken Shreds', 'Salmon Feast', 'Turkey Giblets', 'Kitten Chicken Pate',
                      'Seafood Medley', 'Beef Flaked'), CAN_SIZES),
        CategorySpec('Litter', .20, .10, (8, 35), (.30, .40), 'few',
                     ('Clumping Clay Litter', 'Unscented Clumping Litter', 'Pine Pellet Litter',
                      'Crystal Litter', 'Walnut Shell Litter', 'Multi-Cat Litter'),
                     ('10 lb', '14 lb', '20 lb', '28 lb', '40 lb')),
        CategorySpec('Treats', .10, .12, (3, 15), (.40, .55), 'few',
                     ('Crunchy Treats', 'Lickable Puree', 'Freeze-Dried Chicken', 'Dental Treats',
                      'Catnip Biscuits'), ('2 oz', '3 oz', '6 oz', '12 ct')),
        CategorySpec('Toys', .08, .15, (3, 25), (.45, .60), 'few',
                     ('Feather Wand', 'Catnip Mouse', 'Laser Pointer', 'Ball Track', 'Crinkle Tunnel',
                      'Spring Toys'), ('', '3 pk', '6 pk')),
        CategorySpec('Scratchers & Furniture', .06, .12, (15, 190), (.38, .50), 'single',
                     ('Cardboard Scratcher', 'Sisal Scratching Post', 'Cat Tree', 'Window Perch', 'Cat Condo',
                      'Wall Shelves'), ('Small', 'Medium', 'Large')),
        CategorySpec('Grooming', .04, .08, (5, 30), (.40, .55), 'single',
                     ('Self-Cleaning Brush', 'Waterless Shampoo', 'Nail Clippers', 'Grooming Glove'), ('',)),
        CategorySpec('Health & Wellness', .12, .12, (8, 70), (.30, .45), 'single',
                     ('Flea & Tick Topical', 'Hairball Remedy', 'Calming Diffuser', 'Probiotic Powder',
                      'Lysine Chews', 'Dewormer'), ('Kitten', 'Cat', '30 ct', '60 ct')),
    ]),
    DepartmentSpec('FISH', 'Fish & Aquatics', 0.08, [
        CategorySpec('Live Fish', .18, .06, (2, 30), (.55, .70), 'fish',
                     ('Neon Tetra', 'Betta', 'Guppy', 'Comet Goldfish', 'Fancy Goldfish', 'Platy', 'Molly',
                      'Corydoras Catfish', 'Angelfish', 'Zebra Danio', 'Cherry Barb', 'Oscar',
                      'Bristlenose Pleco', 'Cherry Shrimp', 'Mystery Snail', 'Clownfish'),
                     ('Small', 'Medium', 'Large')),
        CategorySpec('Aquariums & Kits', .12, .16, (25, 400), (.30, .42), 'single',
                     ('Starter Aquarium Kit', 'Rimless Aquarium', 'Betta Kit', 'Aquarium Stand', 'Nano Cube'),
                     ('5 gal', '10 gal', '20 gal', '29 gal', '40 gal', '55 gal', '75 gal')),
        CategorySpec('Filters & Pumps', .15, .18, (10, 150), (.38, .50), 'single',
                     ('Hang-On-Back Filter', 'Canister Filter', 'Sponge Filter', 'Air Pump', 'Powerhead',
                      'Replacement Cartridges'), ('10 gal', '20 gal', '30 gal', '55 gal', '75 gal')),
        CategorySpec('Food', .18, .16, (3, 25), (.40, .55), 'few',
                     ('Tropical Flakes', 'Goldfish Pellets', 'Betta Pellets', 'Bottom Feeder Wafers',
                      'Frozen Bloodworms', 'Marine Pellets'), ('1 oz', '2 oz', '4 oz', '7 oz')),
        CategorySpec('Water Care', .20, .20, (5, 40), (.42, .55), 'few',
                     ('Water Conditioner', 'Biological Booster', 'Freshwater Test Kit', 'pH Down',
                      'Algae Control', 'Aquarium Salt'), ('4 oz', '8 oz', '16 oz', '32 oz')),
        CategorySpec('Decor & Substrate', .17, .24, (4, 60), (.45, .60), 'few',
                     ('Aquarium Gravel', 'Live Plant Bundle', 'Driftwood', 'Resin Castle', 'Artificial Plant',
                      'Background'), ('Small', 'Medium', 'Large', '5 lb', '20 lb')),
    ]),
    DepartmentSpec('BIRD', 'Birds', 0.05, [
        CategorySpec('Live Birds', .20, 0, (0, 0), (.60, .75), 'single', live=True),
        CategorySpec('Food & Seed', .38, .35, (4, 45), (.35, .48), 'few',
                     ('Parakeet Seed Mix', 'Cockatiel Pellets', 'Finch Seed', 'Parrot Fruit Blend',
                      'Millet Spray', 'Canary Song Food'), ('2 lb', '5 lb', '10 lb', '20 lb')),
        CategorySpec('Cages', .14, .20, (30, 300), (.35, .48), 'single',
                     ('Flight Cage', 'Parakeet Cage', 'Travel Carrier', 'Play Top Cage'),
                     ('Small', 'Medium', 'Large')),
        CategorySpec('Toys & Perches', .16, .30, (3, 30), (.45, .60), 'few',
                     ('Rope Perch', 'Mirror Toy', 'Swing', 'Foraging Toy', 'Ladder', 'Mineral Block'),
                     ('Small', 'Medium', 'Large')),
        CategorySpec('Health', .12, .15, (5, 30), (.35, .48), 'single',
                     ('Vitamin Drops', 'Cuttlebone', 'Mite Spray', 'Grit'), ('',)),
    ]),
    DepartmentSpec('SMALL', 'Small Animals', 0.06, [
        CategorySpec('Live Small Animals', .15, 0, (0, 0), (.60, .75), 'single', live=True),
        CategorySpec('Food & Hay', .40, .30, (4, 40), (.35, .48), 'few',
                     ('Timothy Hay', 'Orchard Grass Hay', 'Guinea Pig Pellets', 'Rabbit Pellets',
                      'Hamster Food', 'Rat Block'), ('2 lb', '5 lb', '10 lb', '40 oz')),
        CategorySpec('Bedding', .22, .20, (6, 30), (.40, .52), 'few',
                     ('Paper Bedding', 'Aspen Shavings', 'Pine Bedding', 'Fleece Liner'),
                     ('10 L', '30 L', '60 L', '2-pk')),
        CategorySpec('Habitats', .10, .20, (25, 200), (.35, .48), 'single',
                     ('Hamster Habitat', 'Guinea Pig Cage', 'Rabbit Hutch', 'Exercise Pen', 'Ferret Nation Cage'),
                     ('Small', 'Medium', 'Large')),
        CategorySpec('Toys & Chews', .13, .30, (3, 25), (.45, .60), 'few',
                     ('Exercise Wheel', 'Chew Sticks', 'Hideout', 'Tunnel', 'Hay Feeder', 'Water Bottle'),
                     ('Small', 'Medium', 'Large')),
    ]),
    DepartmentSpec('REP', 'Reptiles', 0.06, [
        CategorySpec('Live Reptiles', .18, 0, (0, 0), (.60, .75), 'single', live=True),
        CategorySpec('Feeders & Food', .30, .18, (3, 25), (.45, .60), 'few',
                     ('Live Crickets', 'Mealworms', 'Dubia Roaches', 'Frozen Mice', 'Turtle Pellets',
                      'Gecko Diet', 'Tortoise Food'), ('25 ct', '50 ct', '100 ct', '6 oz', '12 oz')),
        CategorySpec('Habitats & Terrariums', .12, .20, (40, 350), (.32, .45), 'single',
                     ('Glass Terrarium', 'Front-Opening Terrarium', 'Turtle Tank Kit', 'Screen Enclosure'),
                     ('10 gal', '20 gal', '40 gal', '75 gal', '18x18x24 in')),
        CategorySpec('Heating & Lighting', .20, .24, (10, 90), (.38, .52), 'single',
                     ('UVB Bulb', 'Basking Bulb', 'Ceramic Heat Emitter', 'Under-Tank Heater', 'Thermostat',
                      'Lighting Fixture'), ('50 W', '75 W', '100 W', '150 W', 'Small', 'Large')),
        CategorySpec('Substrate & Decor', .12, .26, (5, 50), (.45, .58), 'few',
                     ('Coconut Fiber Substrate', 'Bioactive Soil', 'Reptile Carpet', 'Hide Cave', 'Basking Rock',
                      'Artificial Vines'), ('Small', 'Medium', 'Large', '8 qt', '24 qt')),
        CategorySpec('Health', .08, .12, (6, 30), (.35, .48), 'single',
                     ('Calcium with D3', 'Multivitamin', 'Mite Spray', 'Shedding Aid'), ('',)),
    ]),
]

# (common name, scientific name, department code, price, popularity weight)
SPECIES = [
    ('Budgerigar', 'Melopsittacus undulatus', 'BIRD', 29.99, 10),
    ('Cockatiel', 'Nymphicus hollandicus', 'BIRD', 149.99, 5),
    ('Lovebird', 'Agapornis roseicollis', 'BIRD', 89.99, 3),
    ('Zebra finch', 'Taeniopygia guttata', 'BIRD', 24.99, 4),
    ('Canary', 'Serinus canaria domestica', 'BIRD', 79.99, 3),
    ('Green-cheeked conure', 'Pyrrhura molinae', 'BIRD', 399.99, 1.5),
    ('Parrotlet', 'Forpus coelestis', 'BIRD', 249.99, 1),
    ('Society finch', 'Lonchura striata domestica', 'BIRD', 24.99, 2),
    ('Syrian hamster', 'Mesocricetus auratus', 'SMALL', 19.99, 8),
    ('Dwarf hamster', 'Phodopus campbelli', 'SMALL', 17.99, 5),
    ('Guinea pig', 'Cavia porcellus', 'SMALL', 44.99, 7),
    ('Rabbit', 'Oryctolagus cuniculus', 'SMALL', 69.99, 4),
    ('Fancy rat', 'Rattus norvegicus domestica', 'SMALL', 19.99, 3),
    ('Fancy mouse', 'Mus musculus', 'SMALL', 7.99, 3),
    ('Gerbil', 'Meriones unguiculatus', 'SMALL', 14.99, 2.5),
    ('Chinchilla', 'Chinchilla lanigera', 'SMALL', 249.99, 1),
    ('Ferret', 'Mustela furo', 'SMALL', 399.99, 1),
    ('Degu', 'Octodon degus', 'SMALL', 39.99, 0.6),
    ('Leopard gecko', 'Eublepharis macularius', 'REP', 79.99, 8),
    ('Crested gecko', 'Correlophus ciliatus', 'REP', 99.99, 4),
    ('Bearded dragon', 'Pogona vitticeps', 'REP', 129.99, 7),
    ('Ball python', 'Python regius', 'REP', 119.99, 5),
    ('Corn snake', 'Pantherophis guttatus', 'REP', 89.99, 4),
    ('Blue-tongued skink', 'Tiliqua scincoides', 'REP', 249.99, 1.2),
    ('Red-eared slider', 'Trachemys scripta elegans', 'REP', 34.99, 3),
    ('Russian tortoise', 'Testudo horsfieldii', 'REP', 199.99, 1.5),
    ('Green anole', 'Anolis carolinensis', 'REP', 12.99, 4),
    ('California kingsnake', 'Lampropeltis californiae', 'REP', 129.99, 1.5),
    ('Veiled chameleon', 'Chamaeleo calyptratus', 'REP', 99.99, 1.5),
    ('African fat-tailed gecko', 'Hemitheconyx caudicinctus', 'REP', 89.99, 1.5),
]

# Brand names are built from these words; each brand sells in one or two departments.
BRAND_FIRST = ['Trail', 'Whisker', 'Harbor', 'Meadow', 'Summit', 'Golden', 'Prairie', 'Cedar', 'Willow', 'Blue',
               'Red Barn', 'True', 'Wild', 'Happy', 'Pure', 'Nature\'s', 'Northern', 'Coastal', 'Evergreen', 'Maple',
               'Sunny', 'Bright', 'Oak', 'River', 'Stone', 'Silver', 'Copper', 'Little', 'Big Sky', 'Honest']
BRAND_SECOND = {
    'DOG': ['Hound', 'Paws', 'Bark', 'Tail', 'Pup', 'Fetch', 'Canine'],
    'CAT': ['Whiskers', 'Purr', 'Kitty', 'Feline', 'Meow', 'Tabby'],
    'FISH': ['Aquatics', 'Reef', 'Tide', 'Current', 'Fin'],
    'BIRD': ['Feather', 'Wing', 'Nest', 'Songbird', 'Perch'],
    'SMALL': ['Burrow', 'Nibbles', 'Critter', 'Hay Co.', 'Whisker Wood'],
    'REP': ['Herp', 'Scales', 'Terra', 'Basking', 'Desert'],
}
HOUSE_BRAND = 'Pets Central Essentials'

QUANTITY_DISTRIBUTIONS = {
    # (values, weights)
    'single': ((1, 2), (.93, .07)),
    'few': ((1, 2, 3, 4), (.70, .20, .07, .03)),
    'cans': ((1, 2, 3, 4, 6, 12, 24), (.30, .15, .12, .13, .12, .13, .05)),
    'fish': ((1, 2, 3, 4, 5, 6, 8, 10, 12), (.25, .14, .12, .08, .10, .14, .06, .07, .04)),
}

# Monthly demand multipliers by category name (month 1-12). Categories not listed use 1.0.
_TOYS = {11: 1.25, 12: 1.9}
CATEGORY_SEASONALITY = {
    'Toys': _TOYS,
    'Treats & Chews': {11: 1.15, 12: 1.6},
    'Treats': {11: 1.15, 12: 1.6},
    'Beds & Crates': {11: 1.2, 12: 1.5},
    'Scratchers & Furniture': {11: 1.2, 12: 1.6},
    'Health & Wellness': {1: .75, 2: .8, 4: 1.25, 5: 1.45, 6: 1.5, 7: 1.5, 8: 1.4, 9: 1.2, 12: .8},
    'Live Fish': {6: 1.25, 7: 1.3, 8: 1.2, 12: 1.3},
    'Aquariums & Kits': {6: 1.15, 7: 1.15, 11: 1.3, 12: 1.8},
    'Live Birds': {3: 1.4, 4: 1.5, 12: 1.3},
    'Live Small Animals': {3: 1.5, 4: 1.6, 8: 1.25, 12: 1.4},
    'Live Reptiles': {6: 1.2, 7: 1.2, 12: 1.4},
    'Heating & Lighting': {1: 1.35, 2: 1.3, 10: 1.2, 11: 1.3, 12: 1.35, 6: .8, 7: .75},
    'Toys & Perches': _TOYS,
    'Toys & Chews': _TOYS,
}

MONTH_FACTOR = {1: .92, 2: .90, 3: .98, 4: 1.0, 5: 1.02, 6: 1.0, 7: 1.0, 8: .99, 9: .95, 10: .98, 11: 1.06, 12: 1.28}
WEEKDAY_FACTOR = [.86, .82, .88, .95, 1.08, 1.30, 1.11]  # Monday first.
ANNUAL_GROWTH = 0.05

CAMPAIGN_THEMES = {
    'DOG': ['Fresh Food Week', 'Treat Yourself (and Your Dog)', 'Flea & Tick Season', 'Back to Walks', 'Puppy Starter'],
    'CAT': ['Indoor Cat Days', 'Litter Box Refresh', 'Kitten Season', 'Purrfect Pantry', 'Scratch That'],
    'FISH': ['Tank Upgrade Days', 'Water Care Month', 'Aquarium Starter'],
    'BIRD': ['Bird Seed Sale', 'Cage Cleaning Week'],
    'SMALL': ['Small Pet Spring', 'Fresh Hay Days'],
    'REP': ['Reptile Heat Wave', 'Feeder Frenzy', 'Herp Habitat Week'],
}
