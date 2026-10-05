// Generated from openapi/order.json by scripts/gen-api.mjs. Do not edit.

export type paths = {
  '/api/orders/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get: operations['orders_list']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/{order_id}/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get: operations['orders_retrieve']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/{order_id}/cancel/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    post: operations['orders_cancel']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/{order_id}/pay/mock/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Pay an order without a provider (development only)
     * @description Takes the same path as a payment.paid event from a provider. Exists only when PAYMENT_MOCK_ENABLED and DEBUG are on; 404 otherwise.
     */
    post: operations['orders_pay_mock']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/{order_id}/status/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** Order status for polling */
    get: operations['orders_status']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/checkout/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Create an order from the cart
     * @description Snapshots current catalog prices and creates a PENDING order; the catalog reserves its stock asynchronously. Poll the status endpoint: PENDING turns into RESERVED (pay before reserved_until) or CANCELLED with cancel_reason OUT_OF_STOCK when the stock could not be held. Retries with the same Idempotency-Key and body replay the first answer.
     */
    post: operations['orders_checkout']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/seller/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** Sub-orders of the current seller, newest first */
    get: operations['seller_orders_list']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/seller/{sub_order_id}/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get: operations['seller_orders_retrieve']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/orders/seller/{sub_order_id}/status/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    /**
     * Accept, ship, deliver or cancel a sub-order
     * @description Allowed: NEW -> ACCEPTED | CANCELLED_BY_SELLER, ACCEPTED -> SHIPPED | CANCELLED_BY_SELLER, SHIPPED -> DELIVERED. SHIPPED needs tracking_number, CANCELLED_BY_SELLER needs reason. The order moves to FULFILLING with the first shipment and to COMPLETED once every sub-order that was not cancelled is delivered.
     */
    patch: operations['seller_orders_set_status']
    trace?: never
  }
  '/api/orders/seller/stats/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /**
     * Dashboard numbers of the current seller
     * @description Days, ISO weeks and calendar months in Asia/Tashkent. Sub-orders cancelled by the seller are left out of orders/gross/net but counted in by_status. net = gross - commission. daily covers the last 30 days including today.
     */
    get: operations['seller_orders_stats']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
}
export type webhooks = Record<string, never>
export type components = {
  schemas: {
    Address: {
      city: string
      full_name: string
      /** @default  */
      notes: string
      phone: string
      region: string
      street: string
    }
    AddressRequest: {
      city: string
      full_name: string
      /** @default  */
      notes: string
      phone: string
      region: string
      street: string
    }
    CheckoutRequest: {
      address: components['schemas']['AddressRequest']
    }
    CheckoutResult: {
      /** Format: uuid */
      order_id: string
      status: components['schemas']['OrderStatusEnum']
    }
    DailyStats: {
      /** Format: date */
      date: string
      gross_tiyin: number
      net_tiyin: number
      orders: number
    }
    Error: {
      error: components['schemas']['ErrorBody']
    }
    ErrorBody: {
      code: string
      details: {
        [key: string]: unknown
      }
      message: string
    }
    /** @enum {unknown} */
    NullEnum: null
    OrderDetail: {
      readonly cancel_reason: string
      /** Format: date-time */
      readonly created_at: string
      delivery_address: components['schemas']['Address']
      history: components['schemas']['OrderHistory'][]
      /** Format: uuid */
      readonly id: string
      readonly late_payment: boolean
      /** Format: date-time */
      readonly reserved_until: string | null
      readonly sellers: components['schemas']['SellerGroup'][]
      readonly status: components['schemas']['OrderStatusEnum']
      readonly total_tiyin: number
      /** Format: date-time */
      readonly updated_at: string
    }
    OrderHistory: {
      /** Format: date-time */
      readonly created_at: string
      from_status:
        (components['schemas']['OrderStatusEnum'] | components['schemas']['NullEnum']) | null
      readonly reason: string
      to_status: components['schemas']['OrderStatusEnum']
    }
    OrderItem: {
      /** Format: uuid */
      readonly id: string
      readonly image_url: string | null
      line_total_tiyin: number
      price_tiyin: number
      readonly qty: number
      sku: string
      title: string
      /** Format: uuid */
      readonly variant_id: string
    }
    OrderStatus: {
      /** Format: date-time */
      readonly reserved_until: string | null
      readonly status: components['schemas']['OrderStatusEnum']
    }
    /**
     * @description * `PENDING` - Pending
     *     * `RESERVED` - Reserved
     *     * `PAID` - Paid
     *     * `FULFILLING` - Fulfilling
     *     * `COMPLETED` - Completed
     *     * `EXPIRED` - Expired
     *     * `CANCELLED` - Cancelled
     *     * `REFUNDED` - Refunded
     * @enum {string}
     */
    OrderStatusEnum:
      | 'PENDING'
      | 'RESERVED'
      | 'PAID'
      | 'FULFILLING'
      | 'COMPLETED'
      | 'EXPIRED'
      | 'CANCELLED'
      | 'REFUNDED'
    OrderSummary: {
      /** Format: date-time */
      readonly created_at: string
      /** Format: uuid */
      readonly id: string
      readonly items_count: number
      /** Format: date-time */
      readonly reserved_until: string | null
      readonly status: components['schemas']['OrderStatusEnum']
      readonly total_tiyin: number
    }
    PaginatedOrderSummaryList: {
      items: components['schemas']['OrderSummary'][]
      page: number
      page_size: number
      total: number
    }
    PaginatedSellerSubOrderList: {
      items: components['schemas']['SellerSubOrder'][]
      page: number
      page_size: number
      total: number
    }
    /** @description SHIPPED needs a tracking number, CANCELLED_BY_SELLER a reason. */
    PatchedSubOrderStatusChangeRequest: {
      reason?: string
      status?: components['schemas']['SubOrderTargetStatusEnum']
      tracking_number?: string
    }
    PeriodStats: {
      gross_tiyin: number
      net_tiyin: number
      orders: number
    }
    /** @description The items of one seller. Sub-order fields stay null (history empty) until payment. */
    SellerGroup: {
      cancel_reason: string | null
      history: components['schemas']['SubOrderHistory'][]
      items: components['schemas']['OrderItem'][]
      /** Format: uuid */
      seller_id: string
      shop_name: string
      status:
        (components['schemas']['SubOrderStatusEnum'] | components['schemas']['NullEnum']) | null
      /** Format: uuid */
      sub_order_id: string | null
      subtotal_tiyin: number
      tracking_number: string | null
    }
    SellerItem: {
      /** Format: uuid */
      readonly id: string
      readonly image: string | null
      line_total_tiyin: number
      price_tiyin: number
      readonly qty: number
      sku: string
      title: string
      /** Format: uuid */
      readonly variant_id: string
    }
    /** @description Tashkent today / ISO week / calendar month, the last 30 days and per-status counts. */
    SellerStats: {
      by_status: components['schemas']['StatusCounts']
      daily: components['schemas']['DailyStats'][]
      month: components['schemas']['PeriodStats']
      today: components['schemas']['PeriodStats']
      week: components['schemas']['PeriodStats']
    }
    /** @description A row of the seller list. Needs ``items_count`` annotated and ``order`` joined. */
    SellerSubOrder: {
      readonly city: string
      readonly commission_tiyin: number
      /** Format: date-time */
      readonly created_at: string
      readonly customer_name: string
      /** Format: uuid */
      readonly id: string
      readonly items_count: number
      readonly net_tiyin: number
      /** Format: uuid */
      readonly order_id: string
      status: components['schemas']['SubOrderStatusEnum']
      readonly subtotal_tiyin: number
      /** Format: date-time */
      readonly updated_at: string
    }
    /** @description One sub-order with everything needed to ship it, including the customer's phone. */
    SellerSubOrderDetail: {
      readonly cancel_reason: string
      readonly city: string
      /** Format: decimal */
      commission_rate: string
      readonly commission_tiyin: number
      /** Format: date-time */
      readonly created_at: string
      readonly customer_name: string
      delivery_address: components['schemas']['Address']
      history: components['schemas']['SubOrderHistory'][]
      /** Format: uuid */
      readonly id: string
      items: components['schemas']['SellerItem'][]
      readonly items_count: number
      readonly net_tiyin: number
      /** Format: uuid */
      readonly order_id: string
      order_status: components['schemas']['OrderStatusEnum']
      status: components['schemas']['SubOrderStatusEnum']
      readonly subtotal_tiyin: number
      readonly tracking_number: string
      /** Format: date-time */
      readonly updated_at: string
    }
    StatusCounts: {
      ACCEPTED: number
      CANCELLED_BY_SELLER: number
      DELIVERED: number
      NEW: number
      SHIPPED: number
    }
    SubOrderHistory: {
      /** Format: date-time */
      readonly created_at: string
      from_status:
        (components['schemas']['SubOrderStatusEnum'] | components['schemas']['NullEnum']) | null
      readonly reason: string
      to_status: components['schemas']['SubOrderStatusEnum']
    }
    /**
     * @description * `NEW` - New
     *     * `ACCEPTED` - Accepted
     *     * `SHIPPED` - Shipped
     *     * `DELIVERED` - Delivered
     *     * `CANCELLED_BY_SELLER` - Cancelled_By_Seller
     * @enum {string}
     */
    SubOrderStatusEnum: 'NEW' | 'ACCEPTED' | 'SHIPPED' | 'DELIVERED' | 'CANCELLED_BY_SELLER'
    /**
     * @description * `ACCEPTED` - Accepted
     *     * `SHIPPED` - Shipped
     *     * `DELIVERED` - Delivered
     *     * `CANCELLED_BY_SELLER` - Cancelled_By_Seller
     * @enum {string}
     */
    SubOrderTargetStatusEnum: 'ACCEPTED' | 'SHIPPED' | 'DELIVERED' | 'CANCELLED_BY_SELLER'
  }
  responses: never
  parameters: never
  requestBodies: never
  headers: never
  pathItems: never
}
export type $defs = Record<string, never>
export interface operations {
  orders_list: {
    parameters: {
      query?: {
        /** @description A page number within the paginated result set. */
        page?: number
        /** @description Number of results to return per page. */
        page_size?: number
      }
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['PaginatedOrderSummaryList']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  orders_retrieve: {
    parameters: {
      query?: never
      header?: never
      path: {
        order_id: string
      }
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['OrderDetail']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_FOUND: no such order of the current user */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  orders_cancel: {
    parameters: {
      query?: never
      header?: never
      path: {
        order_id: string
      }
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['OrderDetail']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_FOUND: no such order of the current user */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description INVALID_TRANSITION: only PENDING or RESERVED */
      409: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  orders_pay_mock: {
    parameters: {
      query?: never
      header?: never
      path: {
        order_id: string
      }
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['OrderDetail']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_FOUND: no such order of the current user */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_RESERVED: still PENDING, try again shortly; ORDER_EXPIRED; INVALID_TRANSITION: cancelled or refunded */
      409: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description SERVICE_UNAVAILABLE: catalog did not answer (commission rates) */
      503: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  orders_status: {
    parameters: {
      query?: never
      header?: never
      path: {
        order_id: string
      }
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['OrderStatus']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_FOUND: no such order of the current user */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  orders_checkout: {
    parameters: {
      query?: never
      header: {
        /** @description Unique per checkout attempt (e.g. a UUID), at most 255 characters. */
        'Idempotency-Key': string
      }
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['CheckoutRequest']
        'application/x-www-form-urlencoded': components['schemas']['CheckoutRequest']
        'multipart/form-data': components['schemas']['CheckoutRequest']
      }
    }
    responses: {
      202: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['CheckoutResult']
        }
      }
      /** @description VALIDATION_ERROR, IDEMPOTENCY_KEY_REQUIRED, IDEMPOTENCY_KEY_INVALID */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description CART_EMPTY; ITEMS_UNAVAILABLE with details.items[{variant_id, reason (not_found|inactive|out_of_stock), available}]; IDEMPOTENCY_KEY_REUSED; IDEMPOTENCY_IN_PROGRESS */
      409: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description SERVICE_UNAVAILABLE: cart, catalog or redis did not answer */
      503: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  seller_orders_list: {
    parameters: {
      query?: {
        /** @description First day, inclusive (Asia/Tashkent). */
        date_from?: string
        /** @description Last day, inclusive (Asia/Tashkent). */
        date_to?: string
        /** @description A page number within the paginated result set. */
        page?: number
        /** @description Number of results to return per page. */
        page_size?: number
        /** @description Repeat the parameter or pass a comma separated list. */
        status?: ('ACCEPTED' | 'CANCELLED_BY_SELLER' | 'DELIVERED' | 'NEW' | 'SHIPPED')[]
      }
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['PaginatedSellerSubOrderList']
        }
      }
      /** @description VALIDATION_ERROR: unknown status or bad date */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description PERMISSION_DENIED: seller role required */
      403: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  seller_orders_retrieve: {
    parameters: {
      query?: never
      header?: never
      path: {
        sub_order_id: string
      }
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerSubOrderDetail']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description PERMISSION_DENIED: seller role required */
      403: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_FOUND: no such sub-order of this seller */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  seller_orders_set_status: {
    parameters: {
      query?: never
      header?: never
      path: {
        sub_order_id: string
      }
      cookie?: never
    }
    requestBody?: {
      content: {
        'application/json': components['schemas']['PatchedSubOrderStatusChangeRequest']
        'application/x-www-form-urlencoded': components['schemas']['PatchedSubOrderStatusChangeRequest']
        'multipart/form-data': components['schemas']['PatchedSubOrderStatusChangeRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerSubOrderDetail']
        }
      }
      /** @description VALIDATION_ERROR: unknown status, missing tracking_number or reason */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description PERMISSION_DENIED: seller role required */
      403: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description NOT_FOUND: no such sub-order of this seller */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description INVALID_TRANSITION with details {from, to}; ORDER_NOT_ACTIVE with details {order_status} */
      409: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  seller_orders_stats: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerStats']
        }
      }
      /** @description NOT_AUTHENTICATED */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description PERMISSION_DENIED: seller role required */
      403: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
}
