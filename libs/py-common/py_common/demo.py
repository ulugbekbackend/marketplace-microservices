"""Demo data shared by the seed commands of several services.

Ids are derived from phone numbers with uuid5, so every service computes the same id for
the same demo person without talking to the others, and re-running a seed changes nothing.
"""

from dataclasses import dataclass
from uuid import UUID, uuid5

DEMO_NAMESPACE = UUID("6f1c2b7e-8d3a-4c55-9e0b-2a7d4f1e9c30")


def demo_id(kind: str, key: str) -> UUID:
    """Stable id for a demo record, e.g. demo_id("user", "+998900000001")."""
    return uuid5(DEMO_NAMESPACE, f"{kind}:{key}")


def demo_user_id(phone: str) -> UUID:
    return demo_id("user", phone)


@dataclass(frozen=True, slots=True)
class DemoSeller:
    phone: str
    full_name: str
    shop_name: str
    inn: str
    description: str

    @property
    def user_id(self) -> UUID:
        return demo_user_id(self.phone)


ADMIN_PHONE = "+998900000001"
ADMIN_NAME = "Bozorcha Admin"

SELLERS: tuple[DemoSeller, ...] = (
    DemoSeller(
        "+998901110001",
        "Jasur Karimov",
        "Texnomart Plus",
        "301234561",
        "Smartfonlar, noutbuklar va maishiy texnika",
    ),
    DemoSeller(
        "+998901110002",
        "Dilnoza Rahimova",
        "Oqtepa Savdo",
        "301234562",
        "Kiyim-kechak va poyabzal",
    ),
    DemoSeller(
        "+998901110003",
        "Sardor Aliyev",
        "Chilonzor Elektronika",
        "301234563",
        "Aksessuarlar va gadjetlar",
    ),
    DemoSeller(
        "+998901110004",
        "Malika Yusupova",
        "Uy Bozori",
        "301234564",
        "Uy-ro'zg'or buyumlari va oshxona jihozlari",
    ),
    DemoSeller(
        "+998901110005",
        "Bekzod Toshmatov",
        "Sport Olami",
        "301234565",
        "Sport kiyimlari va jihozlari",
    ),
)

CUSTOMER_PHONES: tuple[str, ...] = tuple(f"+9989122200{index:02d}" for index in range(1, 21))

CUSTOMER_NAMES: tuple[str, ...] = (
    "Aziz Nazarov",
    "Nodira Qodirova",
    "Otabek Ismoilov",
    "Gulnora Saidova",
    "Rustam Xolmatov",
    "Shahnoza Ergasheva",
    "Farrux Mirzayev",
    "Zarina Abdullayeva",
    "Ulug'bek Sobirov",
    "Kamola Tursunova",
    "Javohir Hamidov",
    "Madina Oripova",
    "Sherzod Ahmedov",
    "Feruza Nurmatova",
    "Anvar Rashidov",
    "Laylo Jo'rayeva",
    "Doniyor Umarov",
    "Sevara Po'latova",
    "Islom Qosimov",
    "Mohira Valiyeva",
)
