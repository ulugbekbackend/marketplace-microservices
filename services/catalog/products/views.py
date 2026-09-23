"""Catalog HTTP API: public storefront reads and the seller cabinet."""

from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from products import queries, services, storage
from products.filters import PublicProductFilter, SellerProductFilter
from products.models import Attribute, Product
from products.serializers import (
    AttributeSerializer,
    CategoryNodeSerializer,
    ImageAttachSerializer,
    PresignRequestSerializer,
    PresignResponseSerializer,
    ProductCardSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
    ProductUpdateSerializer,
    SellerImageSerializer,
    SellerProductDetailSerializer,
    SellerProductSerializer,
    SellerVariantSerializer,
    ShopSerializer,
    StockUpdateSerializer,
    VariantCreateSerializer,
    VariantUpdateSerializer,
)
from py_common.web.drf import IsSeller
from sellers.access import resolve_seller
from sellers.models import Seller

PUBLIC = "catalog"
SELLER = "seller"

# --- public -------------------------------------------------------------------------


class CategoryTreeView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        tags=[PUBLIC],
        operation_id="categories_tree",
        responses=CategoryNodeSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        tree = queries.active_category_tree()
        return Response(CategoryNodeSerializer(tree, many=True).data)


@extend_schema_view(get=extend_schema(tags=[PUBLIC], operation_id="products_list"))
class PublicProductListView(generics.ListAPIView[Product]):
    permission_classes = (AllowAny,)
    serializer_class = ProductCardSerializer
    filterset_class = PublicProductFilter

    def get_queryset(self) -> QuerySet[Product]:
        return queries.public_products()


@extend_schema_view(get=extend_schema(tags=[PUBLIC], operation_id="products_retrieve"))
class PublicProductDetailView(generics.RetrieveAPIView[Product]):
    permission_classes = (AllowAny,)
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"

    def get_queryset(self) -> QuerySet[Product]:
        return queries.public_product_detail()


@extend_schema_view(get=extend_schema(tags=[PUBLIC], operation_id="shops_retrieve"))
class ShopDetailView(generics.RetrieveAPIView[Seller]):
    permission_classes = (AllowAny,)
    serializer_class = ShopSerializer
    lookup_field = "slug"

    def get_queryset(self) -> QuerySet[Seller]:
        return queries.shops()


@extend_schema_view(get=extend_schema(tags=[SELLER], operation_id="attributes_list"))
class AttributeListView(generics.ListAPIView[Attribute]):
    """Attributes with their values, for building the variant matrix."""

    permission_classes = (IsSeller,)
    serializer_class = AttributeSerializer
    pagination_class = None
    queryset = Attribute.objects.prefetch_related("values").order_by("name")


# --- seller -------------------------------------------------------------------------


class SellerMixin(APIView):
    """Resolves the caller's shop after the IsSeller check; unknown shops get 403."""

    permission_classes = (IsSeller,)
    seller: Seller

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        self.seller = resolve_seller(request)

    def own_products(self) -> QuerySet[Product]:
        if getattr(self, "swagger_fake_view", False):
            return Product.objects.none()
        return queries.seller_products(self.seller)

    def product_response(self, product_id: UUID, status_code: int = 200) -> Response:
        product = self.own_products().get(id=product_id)
        return Response(SellerProductDetailSerializer(product).data, status=status_code)


@extend_schema(tags=[SELLER])
class SellerProductListCreateView(SellerMixin, generics.ListAPIView[Product]):
    serializer_class = SellerProductSerializer
    filterset_class = SellerProductFilter

    def get_queryset(self) -> QuerySet[Product]:
        return self.own_products()

    @extend_schema(operation_id="seller_products_list")
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="seller_products_create",
        request=ProductCreateSerializer,
        responses={201: SellerProductDetailSerializer},
    )
    def post(self, request: Request) -> Response:
        data = ProductCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = services.create_product(
            self.seller,
            title=data.validated_data["title"],
            description=data.validated_data["description"],
            category=data.validated_data["category_id"],
            status=data.validated_data["status"],
        )
        return self.product_response(product.id, status.HTTP_201_CREATED)


@extend_schema(tags=[SELLER])
class SellerProductDetailView(SellerMixin, generics.GenericAPIView[Product]):
    serializer_class = SellerProductDetailSerializer
    lookup_url_kwarg = "product_id"

    def get_queryset(self) -> QuerySet[Product]:
        return self.own_products()

    @extend_schema(operation_id="seller_products_retrieve")
    def get(self, request: Request, product_id: UUID) -> Response:
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(
        operation_id="seller_products_update",
        request=ProductUpdateSerializer,
        responses=SellerProductDetailSerializer,
    )
    def patch(self, request: Request, product_id: UUID) -> Response:
        data = ProductUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        services.update_product(
            self.seller,
            product_id,
            title=values.get("title"),
            description=values.get("description"),
            category=values.get("category_id"),
            status=values.get("status"),
        )
        return self.product_response(product_id)

    @extend_schema(
        operation_id="seller_products_archive",
        request=None,
        responses={204: OpenApiResponse(description="Archived (soft delete).")},
    )
    def delete(self, request: Request, product_id: UUID) -> Response:
        services.archive_product(self.seller, product_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=[SELLER])
class SellerVariantCreateView(SellerMixin):
    @extend_schema(
        operation_id="seller_variants_create",
        request=VariantCreateSerializer,
        responses={201: SellerVariantSerializer},
    )
    def post(self, request: Request, product_id: UUID) -> Response:
        data = VariantCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        variant = services.create_variant(self.seller, product_id, **data.validated_data)
        return Response(SellerVariantSerializer(variant).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=[SELLER])
class SellerVariantUpdateView(SellerMixin):
    @extend_schema(
        operation_id="seller_variants_update",
        request=VariantUpdateSerializer,
        responses=SellerVariantSerializer,
    )
    def patch(self, request: Request, variant_id: UUID) -> Response:
        data = VariantUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        variant = services.update_variant(self.seller, variant_id, **data.validated_data)
        return Response(SellerVariantSerializer(variant).data)


@extend_schema(tags=[SELLER])
class SellerVariantStockView(SellerMixin):
    @extend_schema(
        operation_id="seller_variants_stock_update",
        request=StockUpdateSerializer,
        responses={
            200: SellerVariantSerializer,
            409: OpenApiResponse(description="STOCK_BELOW_RESERVED, details.reserved"),
        },
    )
    def patch(self, request: Request, variant_id: UUID) -> Response:
        data = StockUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        variant = services.set_variant_stock(self.seller, variant_id, data.validated_data["stock"])
        return Response(SellerVariantSerializer(variant).data)


@extend_schema(tags=[SELLER])
class PresignUploadView(SellerMixin):
    @extend_schema(
        operation_id="seller_uploads_presign",
        request=PresignRequestSerializer,
        responses=PresignResponseSerializer,
    )
    def post(self, request: Request) -> Response:
        data = PresignRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = services.ensure_own_product(self.seller, data.validated_data["product_id"])
        upload = storage.presign_upload(
            product.id, data.validated_data["content_type"], data.validated_data["size"]
        )
        body = {
            "upload_url": upload.upload_url,
            "key": upload.key,
            "headers": upload.headers,
            "method": "PUT",
            "expires_in": upload.expires_in,
        }
        return Response(PresignResponseSerializer(body).data)


@extend_schema(tags=[SELLER])
class ProductImageCreateView(SellerMixin):
    @extend_schema(
        operation_id="seller_images_create",
        request=ImageAttachSerializer,
        responses={202: SellerImageSerializer},
    )
    def post(self, request: Request, product_id: UUID) -> Response:
        data = ImageAttachSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        image = services.attach_image(self.seller, product_id, data.validated_data["key"])
        return Response(SellerImageSerializer(image).data, status=status.HTTP_202_ACCEPTED)
