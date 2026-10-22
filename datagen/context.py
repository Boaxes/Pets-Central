from dataclasses import dataclass, field

import numpy as np
from faker import Faker
from faker.providers.person.en_US import Provider as PersonProvider


class Names:
    """Draws US first and last names with realistic frequencies, quickly, in bulk."""

    def __init__(self, rng):
        self.rng = rng
        self._lists = {key: (np.array(list(names.keys()), dtype=object),
                             np.array(list(names.values())) / sum(names.values()))
                       for key, names in [('female', PersonProvider.first_names_female),
                                          ('male', PersonProvider.first_names_male),
                                          ('last', PersonProvider.last_names)]}

    def _draw(self, key, n):
        names, weights = self._lists[key]
        return self.rng.choice(names, size=n, p=weights)

    def first_female(self, n):
        return self._draw('female', n)

    def first_male(self, n):
        return self._draw('male', n)

    def last(self, n):
        return self._draw('last', n)


@dataclass
class Context:
    """Everything one generation run shares: settings, random sources and the tables built so far."""

    size: object
    seed: int
    rng: np.random.Generator = field(init=False)
    fake: Faker = field(init=False)
    names: Names = field(init=False)

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)
        self.fake = Faker('en_US')
        self.fake.seed_instance(self.seed)
        self.names = Names(self.rng)

    def log(self, message):
        print(message, flush=True)
