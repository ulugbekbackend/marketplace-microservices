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
     * @description Exists only when PAYMENT_MOCK_ENABLED and DEBUG are on; 404 otherwise.
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
     * @description Snapshots current catalog prices, creates the order and reserves its stock. The answer carries the order id and its status (RESERVED, or CANCELLED when the stock could not be held); poll the status endpoint afterwards. Retries with the same Idempotency-Key and body replay the first answer.
     */
    post: operations['orders_checkout']
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
    /** @description The items of one seller. ``sub_order_id``/``status`` stay null until payment. */
    SellerGroup: {
      items: components['schemas']['OrderItem'][]
      /** Format: uuid */
      seller_id: string
      shop_name: string
      status:
        (components['schemas']['SubOrderStatusEnum'] | components['schemas']['NullEnum']) | null
      /** Format: uuid */
      sub_order_id: string | null
      subtotal_tiyin: number
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
      /** @description INVALID_TRANSITION, ORDER_EXPIRED, NOT_RESERVED */
      409: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description SERVICE_UNAVAILABLE: catalog did not answer */
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
}
