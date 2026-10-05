// Generated from openapi/search.json by scripts/gen-api.mjs. Do not edit.

export type paths = {
  '/api/search': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /**
     * Search
     * @description Full-text product search with filters, sorting and multi-select facets.
     *
     *     Latin and Cyrillic spellings match each other ("telefon" = "телефон"), and every
     *     apostrophe variant of o' / g' is accepted. Price filters and facets use the card
     *     price (the lowest variant price).
     */
    get: operations['search_api_search_get']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/search/suggest': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /**
     * Suggest
     * @description Up to 8 title suggestions for a search box (prefix match, any script).
     */
    get: operations['suggest_api_search_suggest_get']
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
    /** AttributeFacet */
    AttributeFacet: {
      /** Code */
      code: string
      /** Values */
      values: components['schemas']['AttributeValueFacet'][]
    }
    /** AttributeValueFacet */
    AttributeValueFacet: {
      /** Count */
      count: number
      /** Selected */
      selected: boolean
      /** Value */
      value: string
    }
    /** CategoryFacet */
    CategoryFacet: {
      /** Count */
      count: number
      /**
       * Id
       * Format: uuid
       */
      id: string
      /** Name */
      name: string
    }
    /** Facets */
    Facets: {
      /** Attributes */
      attributes: components['schemas']['AttributeFacet'][]
      /** Categories */
      categories: components['schemas']['CategoryFacet'][]
      /** Price Ranges */
      price_ranges: components['schemas']['PriceRangeFacet'][]
    }
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components['schemas']['ValidationError'][]
    }
    /** PriceRangeFacet */
    PriceRangeFacet: {
      /** Count */
      count: number
      /**
       * From Tiyin
       * @description Inclusive lower bound; null = open.
       */
      from_tiyin: number | null
      /** Key */
      key: string
      /**
       * To Tiyin
       * @description Exclusive upper bound; null = open.
       */
      to_tiyin: number | null
    }
    /**
     * SearchItem
     * @description What a product card needs.
     */
    SearchItem: {
      /**
       * Id
       * Format: uuid
       */
      id: string
      /** Image Url */
      image_url?: string | null
      /** In Stock */
      in_stock: boolean
      /**
       * Max Price
       * @description Highest variant price, tiyin.
       */
      max_price: number
      /**
       * Min Price
       * @description Lowest variant price, tiyin.
       */
      min_price: number
      /**
       * Rating
       * @default 0
       */
      rating: number
      /**
       * Seller Id
       * Format: uuid
       */
      seller_id: string
      /** Shop Name */
      shop_name: string
      /** Slug */
      slug: string
      /** Title */
      title: string
    }
    /** SearchResponse */
    SearchResponse: {
      facets: components['schemas']['Facets']
      /** Items */
      items: components['schemas']['SearchItem'][]
      /** Page */
      page: number
      /** Page Size */
      page_size: number
      /** Total */
      total: number
    }
    /**
     * Sort
     * @enum {string}
     */
    Sort: 'relevance' | 'price_asc' | 'price_desc' | 'newest'
    /** Suggestion */
    Suggestion: {
      /**
       * Id
       * Format: uuid
       */
      id: string
      /** Slug */
      slug: string
      /** Title */
      title: string
    }
    /** SuggestResponse */
    SuggestResponse: {
      /** Items */
      items: components['schemas']['Suggestion'][]
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
  }
  responses: never
  parameters: never
  requestBodies: never
  headers: never
  pathItems: never
}
export type $defs = Record<string, never>
export interface operations {
  search_api_search_get: {
    parameters: {
      query?: {
        /** @description Attribute filters: `attr[color]=red&attr[color]=blue&attr[size]=M`. Values of one code are OR-ed, different codes are AND-ed. */
        attr?: {
          [key: string]: string
        }
        /** @description Category or any ancestor. */
        category?: string | null
        in_stock?: boolean | null
        page?: number
        page_size?: number
        /** @description Tiyin, inclusive. */
        price_max?: number | null
        /** @description Tiyin, inclusive. */
        price_min?: number | null
        q?: string
        seller?: string | null
        sort?: components['schemas']['Sort']
      }
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
          'application/json': components['schemas']['SearchResponse']
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
  suggest_api_search_suggest_get: {
    parameters: {
      query?: {
        q?: string
      }
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
          'application/json': components['schemas']['SuggestResponse']
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
}
