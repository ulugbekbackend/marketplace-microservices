import type {
  OrderListParams,
  ProductListParams,
  SearchParams,
  SellerOrderListParams,
  SellerPayoutListParams,
  SellerProductListParams,
} from '../types'

/** Query key factory: one place to build and invalidate cache keys. */
export const queryKeys = {
  me: ['auth', 'me'] as const,
  categories: ['catalog', 'categories'] as const,
  products: (params: ProductListParams) => ['catalog', 'products', params] as const,
  product: (slug: string) => ['catalog', 'product', slug] as const,
  shop: (slug: string) => ['catalog', 'shop', slug] as const,
  /** Prefix of every search query (results and suggestions). */
  search: ['search'] as const,
  searchResults: (params: SearchParams) => ['search', 'results', params] as const,
  suggest: (q: string) => ['search', 'suggest', q] as const,
  /** The current cart: the guest's (cookie) or, after login and merge, the customer's. */
  cart: ['cart'] as const,
  /** Kept outside the `cart` prefix so cart invalidations leave favorites alone. */
  favorites: ['favorites'] as const,
  /** Prefix of every order query (list, detail, status). */
  orders: ['orders'] as const,
  orderList: (params: OrderListParams) => ['orders', 'list', params] as const,
  order: (id: string) => ['orders', 'detail', id] as const,
  orderStatus: (id: string) => ['orders', 'status', id] as const,
  /** The caller's latest seller application. */
  sellerApplication: ['auth', 'seller-application'] as const,
  attributes: ['catalog', 'attributes'] as const,
  /** Prefix of every seller cabinet catalog query (lists and details). */
  sellerProducts: ['seller', 'products'] as const,
  sellerProductList: (params: SellerProductListParams) =>
    ['seller', 'products', 'list', params] as const,
  sellerProduct: (id: string) => ['seller', 'products', 'detail', id] as const,
  /** Prefix of every seller order query (lists, details, stats). */
  sellerOrders: ['seller', 'orders'] as const,
  sellerOrderList: (params: SellerOrderListParams) => ['seller', 'orders', 'list', params] as const,
  sellerOrder: (id: string) => ['seller', 'orders', 'detail', id] as const,
  /** Prefix of every seller payout query. */
  sellerPayouts: ['seller', 'payouts'] as const,
  sellerPayoutList: (params: SellerPayoutListParams) => ['seller', 'payouts', params] as const,
  sellerOrderStats: ['seller', 'orders', 'stats'] as const,
}
