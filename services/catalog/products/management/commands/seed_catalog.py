"""Demo catalog: the demo sellers' shops, a three level category tree, 150 products with
about 400 variants, and a generated placeholder picture per product.

Idempotent: shops are created through the same event handler production uses (with a
stable event id), categories and attributes are matched by slug/code, and a product that
already exists for its seller is left alone. Nothing is downloaded from the internet.
"""

import io
import itertools
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from PIL import Image, ImageDraw, ImageFont

from contracts.enums import ProductStatus
from contracts.events import SellerApproved, build_event
from products import storage
from products.models import Attribute, AttributeValue, Category, Product
from products.services import attach_image, create_product, create_variant
from py_common.demo import SELLERS, DemoSeller, demo_id
from sellers.models import Seller
from sellers.services import handle_seller_approved
from slugs import base_slug

TREE: dict[str, dict[str, list[str]]] = {
    "Elektronika": {
        "Telefonlar": ["Smartfonlar", "Tugmali telefonlar"],
        "Noutbuklar": ["Ultrabuklar", "O'yin noutbuklari"],
        "Aksessuarlar": ["Quloqchinlar", "Quvvatlagichlar", "G'iloflar"],
    },
    "Kiyim": {
        "Erkaklar kiyimi": ["Futbolkalar", "Shimlar"],
        "Ayollar kiyimi": ["Ko'ylaklar", "Bluzkalar"],
        "Poyabzal": ["Krossovkalar", "Tuflilar"],
    },
    "Uy-ro'zg'or": {
        "Oshxona": ["Idishlar", "Choynaklar"],
        "Maishiy texnika": ["Changyutgichlar", "Blenderlar"],
    },
    "Sport": {
        "Fitnes": ["Gantellar", "Gilamchalar"],
        "Velosport": ["Velosipedlar"],
    },
}

ATTRIBUTES: dict[str, tuple[str, list[str]]] = {
    "color": ("Rang", ["qora", "oq", "ko'k", "qizil", "kulrang", "yashil"]),
    "memory": ("Xotira", ["64 GB", "128 GB", "256 GB", "512 GB"]),
    "size": ("O'lcham", ["S", "M", "L", "XL"]),
    "shoe_size": ("Poyabzal o'lchami", ["39", "40", "41", "42", "43", "44"]),
    "weight": ("Og'irlik", ["2 kg", "5 kg", "10 kg"]),
}


@dataclass(frozen=True)
class LeafPlan:
    seller: int  # index into SELLERS
    brands: tuple[str, ...]
    noun: str
    price_som: tuple[int, int]
    axes: tuple[str, ...]  # attribute codes that form the variants
    count: int


PLANS: dict[str, LeafPlan] = {
    "Smartfonlar": LeafPlan(
        0,
        ("Samsung Galaxy", "Xiaomi Redmi", "Apple iPhone", "Honor"),
        "",
        (2_500_000, 18_000_000),
        ("color", "memory"),
        18,
    ),
    "Tugmali telefonlar": LeafPlan(0, ("Nokia", "Itel"), "", (180_000, 450_000), ("color",), 5),
    "Ultrabuklar": LeafPlan(
        0,
        ("Lenovo IdeaPad", "HP Pavilion", "Asus Zenbook"),
        "",
        (6_500_000, 16_000_000),
        ("memory",),
        8,
    ),
    "O'yin noutbuklari": LeafPlan(
        0, ("Asus TUF", "Acer Nitro", "MSI Katana"), "", (9_000_000, 22_000_000), ("memory",), 6
    ),
    "Quloqchinlar": LeafPlan(
        2, ("JBL", "Sony", "Xiaomi"), "quloqchin", (150_000, 2_500_000), ("color",), 9
    ),
    "Quvvatlagichlar": LeafPlan(
        2, ("Anker", "Baseus", "Ugreen"), "quvvatlagich", (80_000, 450_000), (), 7
    ),
    "G'iloflar": LeafPlan(2, ("Spigen", "Nillkin"), "g'ilof", (40_000, 250_000), ("color",), 6),
    "Futbolkalar": LeafPlan(
        1, ("Oqtepa", "Basic", "Urban"), "futbolka", (60_000, 250_000), ("size", "color"), 12
    ),
    "Shimlar": LeafPlan(1, ("Oqtepa", "Denim Co"), "shim", (150_000, 450_000), ("size",), 7),
    "Ko'ylaklar": LeafPlan(
        1, ("Gulnoza", "Lola"), "ko'ylak", (200_000, 900_000), ("size", "color"), 8
    ),
    "Bluzkalar": LeafPlan(1, ("Gulnoza", "Sitora"), "bluzka", (120_000, 400_000), ("size",), 6),
    "Krossovkalar": LeafPlan(
        4, ("Nike", "Adidas", "Puma"), "krossovka", (450_000, 1_900_000), ("shoe_size",), 12
    ),
    "Tuflilar": LeafPlan(
        1, ("Classic", "Milano"), "tufli", (300_000, 1_200_000), ("shoe_size",), 6
    ),
    "Idishlar": LeafPlan(3, ("Tefal", "Berghoff"), "idish to'plami", (250_000, 2_000_000), (), 7),
    "Choynaklar": LeafPlan(
        3, ("Philips", "Xiaomi", "Tefal"), "elektr choynak", (180_000, 700_000), ("color",), 6
    ),
    "Changyutgichlar": LeafPlan(
        3, ("Samsung", "Dyson", "Philips"), "changyutgich", (900_000, 7_500_000), (), 6
    ),
    "Blenderlar": LeafPlan(
        3, ("Bosch", "Philips", "Braun"), "blender", (350_000, 1_500_000), (), 6
    ),
    "Gantellar": LeafPlan(4, ("Torres", "Atlas"), "gantel", (90_000, 600_000), ("weight",), 6),
    "Gilamchalar": LeafPlan(
        4, ("Yoga Pro", "Torres"), "fitnes gilamchasi", (80_000, 350_000), ("color",), 5
    ),
    "Velosipedlar": LeafPlan(
        4, ("Stels", "Forward", "Giant"), "velosiped", (1_800_000, 9_000_000), ("color",), 4
    ),
}

PALETTE = ("#0F6E56", "#1E8A4C", "#2F6FB5", "#6B4BC4", "#C63D2F", "#EF9F27", "#37332F")


def _som(value: int) -> int:
    """Round a so'm price to a shop-like number (…000) and return tiyin."""
    return (value // 1_000) * 1_000 * 100


def _placeholder(title: str, color: str) -> bytes:
    image = Image.new("RGB", (800, 800), color)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    words, lines, line = title.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) > 680 and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    lines.append(line)
    y = 400 - len(lines) * 30
    for text in lines:
        width = draw.textlength(text, font=font)
        draw.text(((800 - width) / 2, y), text, fill="white", font=font)
        y += 60
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Create the demo catalog. Safe to run repeatedly."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--no-images", action="store_true", help="Skip generating placeholder pictures."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        with_images = not options["no_images"]
        sellers = [self._seller(seller) for seller in SELLERS]
        leaves = self._categories()
        values = self._attributes()
        rng = random.Random(20260923)

        created = variants = 0
        for leaf_name, plan in PLANS.items():
            seller = sellers[plan.seller]
            for index in range(plan.count):
                brand = plan.brands[index % len(plan.brands)]
                title = " ".join(
                    part for part in (brand, f"{index + 1}0{index % 3}", plan.noun) if part
                )
                if Product.objects.filter(seller=seller, title=title).exists():
                    continue
                product = create_product(
                    seller,
                    title=title,
                    category=leaves[leaf_name],
                    description=(
                        f"{title} — {seller.shop_name} do'konidan. "
                        "Rasmiy kafolat, tez yetkazib berish."
                    ),
                    status=ProductStatus.ACTIVE.value,
                )
                variants += self._variants(seller, product, plan, values, rng)
                if with_images:
                    self._image(seller, product, PALETTE[created % len(PALETTE)])
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"catalog ready: {len(sellers)} shops, {Category.objects.count()} categories, "
                f"{created} new products, {variants} new variants"
            )
        )

    def _seller(self, demo: DemoSeller) -> Seller:
        envelope = build_event(
            SellerApproved(user_id=demo.user_id, shop_name=demo.shop_name),
            producer="auth",
            correlation_id=demo.user_id,
            occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
            event_id=demo_id("seller-approved", demo.phone),
        )
        handle_seller_approved(envelope)
        return Seller.objects.get(id=demo.user_id)

    def _categories(self) -> dict[str, Category]:
        def node(name: str, parent: Category | None) -> Category:
            category, _ = Category.objects.get_or_create(
                slug=base_slug(name if parent is None else f"{parent.slug} {name}", max_length=140),
                defaults={"name": name, "parent": parent},
            )
            return category

        leaves: dict[str, Category] = {}
        for root_name, groups in TREE.items():
            root = node(root_name, None)
            for group_name, leaf_names in groups.items():
                group = node(group_name, root)
                for leaf_name in leaf_names:
                    leaves[leaf_name] = node(leaf_name, group)
        return leaves

    def _attributes(self) -> dict[str, list[AttributeValue]]:
        values: dict[str, list[AttributeValue]] = {}
        for code, (name, options) in ATTRIBUTES.items():
            attribute, _ = Attribute.objects.get_or_create(code=code, defaults={"name": name})
            values[code] = [
                AttributeValue.objects.get_or_create(attribute=attribute, value=option)[0]
                for option in options
            ]
        return values

    def _variants(
        self,
        seller: Seller,
        product: Product,
        plan: LeafPlan,
        values: dict[str, list[AttributeValue]],
        rng: random.Random,
    ) -> int:
        base = rng.randint(*plan.price_som)
        if not plan.axes:
            combos: list[tuple[AttributeValue, ...]] = [()]
        else:
            pools = [
                rng.sample(values[axis], k=min(len(values[axis]), 2 if len(plan.axes) > 1 else 3))
                for axis in plan.axes
            ]
            combos = list(itertools.product(*pools))
        for number, combo in enumerate(combos, start=1):
            step = 1 + 0.15 * sum(
                values[axis].index(value)
                for axis, value in zip(plan.axes, combo, strict=True)
                if axis == "memory"
            )
            create_variant(
                seller,
                product.id,
                sku=f"{product.slug[:40]}-{number}".upper(),
                price_tiyin=_som(int(base * step)),
                stock=rng.choice((0, 3, 5, 10, 25, 50)) if number > 1 else rng.randint(5, 40),
                attribute_value_ids=[value.id for value in combo],
            )
        return len(combos)

    def _image(self, seller: Seller, product: Product, color: str) -> None:
        key = storage.new_original_key(product.id, "image/png")
        storage.upload(key, _placeholder(product.title, color), "image/png")
        attach_image(seller, product.id, key)
