// Generated from openapi/cart.json by scripts/gen-api.mjs. Do not edit.

export type paths = {
  '/api/cart/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /**
     * Get Cart
     * @description Items grouped by seller, with the current price and stock from the catalog.
     */
    get: operations['get_cart_api_cart__get']
    put?: never
    post?: never
    /** Clear Cart */
    delete: operations['clear_cart_api_cart__delete']
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/cart/favorites/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** List Favorites */
    get: operations['list_favorites_api_cart_favorites__get']
    put?: never
    /**
     * Add Favorite
     * @description Idempotent: adding a product twice keeps one entry.
     */
    post: operations['add_favorite_api_cart_favorites__post']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/cart/favorites/{product_id}/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    post?: never
    /** Remove Favorite */
    delete: operations['remove_favorite_api_cart_favorites__product_id___delete']
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/cart/items/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Add Item
     * @description Add units of a variant; an item already in the cart grows (up to 99).
     */
    post: operations['add_item_api_cart_items__post']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/cart/items/{variant_id}/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    post?: never
    /** Remove Item */
    delete: operations['remove_item_api_cart_items__variant_id___delete']
    options?: never
    head?: never
    /**
     * Update Item
     * @description Set the quantity; 0 removes the item.
     */
    patch: operations['update_item_api_cart_items__variant_id___patch']
    trace?: never
  }
  '/api/cart/merge/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Merge Cart
     * @description Right after login: move the guest cart (cookie) into the customer's cart.
     */
    post: operations['merge_cart_api_cart_merge__post']
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
    /** AddItemIn */
    AddItemIn: {
      /**
       * Qty
       * @default 1
       */
      qty: number
      /**
       * Variant Id
       * Format: uuid
       */
      variant_id: string
    }
    /** CartItemOut */
    CartItemOut: {
      /** Attributes */
      attributes: components['schemas']['VariantAttribute'][]
      /**
       * Available
       * @description Active and enough stock for the requested quantity.
       */
      available: boolean
      /**
       * Available Qty
       * @description Units the catalog can still sell right now.
       */
      available_qty: number
      /** Image Url */
      image_url: string | null
      /** Line Total Tiyin */
      line_total_tiyin: number
      /**
       * Previous Price Tiyin
       * @description The price the customer saw, when it changed.
       */
      previous_price_tiyin: number | null
      /**
       * Price Changed
       * @description The price differs from the one the customer saw.
       */
      price_changed: boolean
      /**
       * Price Tiyin
       * @description Current catalog price.
       */
      price_tiyin: number
      /**
       * Product Id
       * Format: uuid
       */
      product_id: string
      /** Product Slug */
      product_slug: string
      /** Qty */
      qty: number
      /** Sku */
      sku: string
      /** Title */
      title: string
      /**
       * Variant Id
       * Format: uuid
       */
      variant_id: string
    }
    /** CartOut */
    CartOut: {
      /** Groups */
      groups: components['schemas']['SellerGroupOut'][]
      /** Has Price Changes */
      has_price_changes: boolean
      /** Has Unavailable */
      has_unavailable: boolean
      /**
       * Items Count
       * @description Total quantity of all items.
       */
      items_count: number
      /**
       * Removed
       * @description Variants dropped from the cart because they no longer exist.
       */
      removed: string[]
      /**
       * Total Tiyin
       * @description Sum of the available items only.
       */
      total_tiyin: number
    }
    /** FavoriteIn */
    FavoriteIn: {
      /**
       * Product Id
       * Format: uuid
       */
      product_id: string
    }
    /** FavoritesOut */
    FavoritesOut: {
      /** Items */
      items: string[]
    }
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components['schemas']['ValidationError'][]
    }
    /** SellerGroupOut */
    SellerGroupOut: {
      /** Items */
      items: components['schemas']['CartItemOut'][]
      /**
       * Seller Id
       * Format: uuid
       */
      seller_id: string
      /** Shop Name */
      shop_name: string
      /**
       * Subtotal Tiyin
       * @description Sum of the available items only.
       */
      subtotal_tiyin: number
    }
    /** UpdateItemIn */
    UpdateItemIn: {
      /**
       * Qty
       * @description 0 removes the item.
       */
      qty: number
    }
    /** ValidationError */
    ValidationError: {
      /** Context */
      ctx?: Record<string, never>
      /** Input */
      input?: unknown
      /** Location */
      loc: (string | number)[]
      /** Message */
      msg: string
      /** Error Type */
      type: string
    }
    /** VariantAttribute */
    VariantAttribute: {
      /** Code */
      code: string
      /** Name */
      name: string
      /** Value */
      value: string
    }
  }
  responses: never
  parameters: never
  requestBodies: never
  headers: never
  pathItems: never
}
export type $defs = Record<string, never>
export interface operations {
  get_cart_api_cart__get: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['CartOut']
        }
      }
    }
  }
  clear_cart_api_cart__delete: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
    }
  }
  list_favorites_api_cart_favorites__get: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['FavoritesOut']
        }
      }
    }
  }
  add_favorite_api_cart_favorites__post: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['FavoriteIn']
      }
    }
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['FavoritesOut']
        }
      }
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['HTTPValidationError']
        }
      }
    }
  }
  remove_favorite_api_cart_favorites__product_id___delete: {
    parameters: {
      query?: never
      header?: never
      path: {
        product_id: string
      }
      cookie?: never
    }
    requestBody?: never
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['HTTPValidationError']
        }
      }
    }
  }
  add_item_api_cart_items__post: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['AddItemIn']
      }
    }
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['CartOut']
        }
      }
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['HTTPValidationError']
        }
      }
    }
  }
  remove_item_api_cart_items__variant_id___delete: {
    parameters: {
      query?: never
      header?: never
      path: {
        variant_id: string
      }
      cookie?: never
    }
    requestBody?: never
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['CartOut']
        }
      }
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['HTTPValidationError']
        }
      }
    }
  }
  update_item_api_cart_items__variant_id___patch: {
    parameters: {
      query?: never
      header?: never
      path: {
        variant_id: string
      }
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['UpdateItemIn']
      }
    }
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['CartOut']
        }
      }
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['HTTPValidationError']
        }
      }
    }
  }
  merge_cart_api_cart_merge__post: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['CartOut']
        }
      }
    }
  }
}
