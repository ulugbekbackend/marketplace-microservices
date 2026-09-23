// Generated from openapi/catalog.json by scripts/gen-api.mjs. Do not edit.

export type paths = {
  '/api/catalog/attributes/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** @description Attributes with their values, for building the variant matrix. */
    get: operations['attributes_list']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/categories/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get: operations['categories_tree']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/products/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get: operations['products_list']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/products/{slug}/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get: operations['products_retrieve']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/seller/products/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    get: operations['seller_products_list']
    put?: never
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    post: operations['seller_products_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/seller/products/{product_id}/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    get: operations['seller_products_retrieve']
    put?: never
    post?: never
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    delete: operations['seller_products_archive']
    options?: never
    head?: never
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    patch: operations['seller_products_update']
    trace?: never
  }
  '/api/catalog/seller/products/{product_id}/images/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    post: operations['seller_images_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/seller/products/{product_id}/variants/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    post: operations['seller_variants_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/seller/uploads/presign/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    post: operations['seller_uploads_presign']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/catalog/seller/variants/{variant_id}/': {
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
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    patch: operations['seller_variants_update']
    trace?: never
  }
  '/api/catalog/seller/variants/{variant_id}/stock/': {
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
    /** @description Resolves the caller's shop after the IsSeller check; unknown shops get 403. */
    patch: operations['seller_variants_stock_update']
    trace?: never
  }
  '/api/catalog/shops/{slug}/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get: operations['shops_retrieve']
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
    Attribute: {
      code: string
      /** Format: uuid */
      readonly id: string
      name: string
      readonly values: components['schemas']['AttributeValue'][]
    }
    AttributeValue: {
      /** Format: uuid */
      readonly id: string
      value: string
    }
    CategoryNode: {
      children: components['schemas']['CategoryNode'][]
      /** Format: uuid */
      id: string
      name: string
      slug: string
    }
    CategoryRef: {
      /** Format: uuid */
      readonly id: string
      name: string
      slug: string
    }
    Image: {
      /** Format: uuid */
      readonly id: string
      readonly large_url: string | null
      readonly medium_url: string | null
      position?: number
      readonly thumb_url: string | null
    }
    ImageAttachRequest: {
      key: string
    }
    /**
     * @description * `image/jpeg` - image/jpeg
     *     * `image/png` - image/png
     *     * `image/webp` - image/webp
     * @enum {string}
     */
    ImageContentTypeEnum: 'image/jpeg' | 'image/png' | 'image/webp'
    /**
     * @description * `processing` - Processing
     *     * `ready` - Ready
     *     * `failed` - Failed
     * @enum {string}
     */
    ImageStatusEnum: 'processing' | 'ready' | 'failed'
    PaginatedProductCardList: {
      items: components['schemas']['ProductCard'][]
      page: number
      page_size: number
      total: number
    }
    PaginatedSellerProductList: {
      items: components['schemas']['SellerProduct'][]
      page: number
      page_size: number
      total: number
    }
    PatchedProductUpdateRequest: {
      /** Format: uuid */
      category_id?: string
      description?: string
      status?: components['schemas']['ProductStatusEnum']
      title?: string
    }
    PatchedStockUpdateRequest: {
      stock?: number
    }
    PatchedVariantUpdateRequest: {
      is_active?: boolean
      price_tiyin?: number
      sku?: string
    }
    PresignRequestRequest: {
      content_type: components['schemas']['ImageContentTypeEnum']
      filename: string
      /**
       * Format: uuid
       * @description The seller's product the image is for.
       */
      product_id: string
      /** @description File size in bytes. */
      size: number
    }
    PresignResponse: {
      /** @description Seconds the URL stays valid. */
      expires_in: number
      /** @description Headers the PUT request must carry. */
      headers: {
        [key: string]: string
      }
      /** @description Send it to the images endpoint after the upload. */
      key: string
      method: string
      /**
       * Format: uri
       * @description PUT the file here.
       */
      upload_url: string
    }
    ProductCard: {
      readonly category: components['schemas']['CategoryRef']
      /** Format: date-time */
      readonly created_at: string
      /** Format: uuid */
      readonly id: string
      readonly image_url: string | null
      readonly in_stock: boolean
      /** @description Highest active variant price, tiyin. */
      readonly max_price_tiyin: number | null
      /** @description Lowest active variant price, tiyin. */
      readonly min_price_tiyin: number | null
      readonly seller: components['schemas']['SellerCard']
      slug: string
      title: string
    }
    ProductCreateRequest: {
      /**
       * Format: uuid
       * @description An active category.
       */
      category_id: string
      /** @default  */
      description: string
      /**
       * @description draft or active; a new product cannot start archived.
       *
       *     * `draft` - Draft
       *     * `active` - Active
       *     * `archived` - Archived
       * @default draft
       */
      status: components['schemas']['ProductStatusEnum']
      title: string
    }
    ProductDetail: {
      readonly breadcrumbs: components['schemas']['CategoryRef'][]
      readonly category: components['schemas']['CategoryRef']
      /** Format: date-time */
      readonly created_at: string
      description?: string
      /** Format: uuid */
      readonly id: string
      readonly image_url: string | null
      readonly images: components['schemas']['Image'][]
      readonly in_stock: boolean
      /** @description Highest active variant price, tiyin. */
      readonly max_price_tiyin: number | null
      /** @description Lowest active variant price, tiyin. */
      readonly min_price_tiyin: number | null
      readonly seller: components['schemas']['SellerCard']
      slug: string
      title: string
      /** Format: date-time */
      readonly updated_at: string
      readonly variants: components['schemas']['PublicVariant'][]
    }
    /**
     * @description * `draft` - Draft
     *     * `active` - Active
     *     * `archived` - Archived
     * @enum {string}
     */
    ProductStatusEnum: 'draft' | 'active' | 'archived'
    PublicVariant: {
      readonly attributes: components['schemas']['VariantAttribute'][]
      /** @description Units a customer can still buy: stock not held by an active reservation. */
      readonly available: number
      /** Format: uuid */
      readonly id: string
      readonly in_stock: boolean
      /** Format: int64 */
      price_tiyin: number
      sku: string
    }
    SellerCard: {
      /** Format: uuid */
      id: string
      is_verified?: boolean
      shop_name: string
      slug: string
    }
    SellerImage: {
      /** Format: date-time */
      readonly created_at: string
      /** Format: uuid */
      readonly id: string
      readonly large_url: string | null
      readonly medium_url: string | null
      original_key: string
      position?: number
      status?: components['schemas']['ImageStatusEnum']
      readonly thumb_url: string | null
    }
    SellerProduct: {
      readonly category: components['schemas']['CategoryRef']
      /** Format: date-time */
      readonly created_at: string
      /** Format: uuid */
      readonly id: string
      readonly image_url: string | null
      readonly in_stock: boolean
      /** @description Highest active variant price, tiyin. */
      readonly max_price_tiyin: number | null
      /** @description Lowest active variant price, tiyin. */
      readonly min_price_tiyin: number | null
      slug: string
      status?: components['schemas']['ProductStatusEnum']
      title: string
      /** Format: date-time */
      readonly updated_at: string
      readonly variants_count: number
    }
    SellerProductDetail: {
      readonly category: components['schemas']['CategoryRef']
      /** Format: date-time */
      readonly created_at: string
      description?: string
      /** Format: uuid */
      readonly id: string
      readonly image_url: string | null
      readonly images: components['schemas']['SellerImage'][]
      readonly in_stock: boolean
      /** @description Highest active variant price, tiyin. */
      readonly max_price_tiyin: number | null
      /** @description Lowest active variant price, tiyin. */
      readonly min_price_tiyin: number | null
      slug: string
      status?: components['schemas']['ProductStatusEnum']
      title: string
      /** Format: date-time */
      readonly updated_at: string
      readonly variants: components['schemas']['SellerVariant'][]
      readonly variants_count: number
    }
    SellerVariant: {
      readonly attributes: components['schemas']['VariantAttribute'][]
      /** @description stock - reserved */
      readonly available: number
      /** Format: date-time */
      readonly created_at: string
      /** Format: uuid */
      readonly id: string
      is_active?: boolean
      /** Format: int64 */
      price_tiyin: number
      reserved?: number
      sku: string
      stock?: number
      /** Format: date-time */
      readonly updated_at: string
    }
    Shop: {
      /** Format: date-time */
      readonly created_at: string
      /** Format: uuid */
      id: string
      is_verified?: boolean
      readonly product_count: number
      shop_name: string
      slug: string
    }
    /** @description One attribute value of a variant, e.g. color = red. */
    VariantAttribute: {
      readonly code: string
      readonly name: string
      value: string
      /** Format: uuid */
      readonly value_id: string
    }
    VariantCreateRequest: {
      attribute_value_ids?: string[]
      /** @description Price in tiyin. */
      price_tiyin: number
      sku: string
      stock: number
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
  attributes_list: {
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
          'application/json': components['schemas']['Attribute'][]
        }
      }
    }
  }
  categories_tree: {
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
          'application/json': components['schemas']['CategoryNode'][]
        }
      }
    }
  }
  products_list: {
    parameters: {
      query?: {
        /** @description Category slug; products of subcategories too. */
        category?: string
        /** @description A page number within the paginated result set. */
        page?: number
        /** @description Number of results to return per page. */
        page_size?: number
        /** @description Shop slug. */
        seller?: string
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
          'application/json': components['schemas']['PaginatedProductCardList']
        }
      }
    }
  }
  products_retrieve: {
    parameters: {
      query?: never
      header?: never
      path: {
        slug: string
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
          'application/json': components['schemas']['ProductDetail']
        }
      }
    }
  }
  seller_products_list: {
    parameters: {
      query?: {
        /** @description A page number within the paginated result set. */
        page?: number
        /** @description Number of results to return per page. */
        page_size?: number
        /** @description Search in title, slug and SKU. */
        q?: string
        /**
         * @description * `draft` - Draft
         *     * `active` - Active
         *     * `archived` - Archived
         */
        status?: 'active' | 'archived' | 'draft'
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
          'application/json': components['schemas']['PaginatedSellerProductList']
        }
      }
    }
  }
  seller_products_create: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['ProductCreateRequest']
        'application/x-www-form-urlencoded': components['schemas']['ProductCreateRequest']
        'multipart/form-data': components['schemas']['ProductCreateRequest']
      }
    }
    responses: {
      201: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerProductDetail']
        }
      }
    }
  }
  seller_products_retrieve: {
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
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerProductDetail']
        }
      }
    }
  }
  seller_products_archive: {
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
      /** @description Archived (soft delete). */
      204: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
    }
  }
  seller_products_update: {
    parameters: {
      query?: never
      header?: never
      path: {
        product_id: string
      }
      cookie?: never
    }
    requestBody?: {
      content: {
        'application/json': components['schemas']['PatchedProductUpdateRequest']
        'application/x-www-form-urlencoded': components['schemas']['PatchedProductUpdateRequest']
        'multipart/form-data': components['schemas']['PatchedProductUpdateRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerProductDetail']
        }
      }
    }
  }
  seller_images_create: {
    parameters: {
      query?: never
      header?: never
      path: {
        product_id: string
      }
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['ImageAttachRequest']
        'application/x-www-form-urlencoded': components['schemas']['ImageAttachRequest']
        'multipart/form-data': components['schemas']['ImageAttachRequest']
      }
    }
    responses: {
      202: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerImage']
        }
      }
    }
  }
  seller_variants_create: {
    parameters: {
      query?: never
      header?: never
      path: {
        product_id: string
      }
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['VariantCreateRequest']
        'application/x-www-form-urlencoded': components['schemas']['VariantCreateRequest']
        'multipart/form-data': components['schemas']['VariantCreateRequest']
      }
    }
    responses: {
      201: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerVariant']
        }
      }
    }
  }
  seller_uploads_presign: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['PresignRequestRequest']
        'application/x-www-form-urlencoded': components['schemas']['PresignRequestRequest']
        'multipart/form-data': components['schemas']['PresignRequestRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['PresignResponse']
        }
      }
    }
  }
  seller_variants_update: {
    parameters: {
      query?: never
      header?: never
      path: {
        variant_id: string
      }
      cookie?: never
    }
    requestBody?: {
      content: {
        'application/json': components['schemas']['PatchedVariantUpdateRequest']
        'application/x-www-form-urlencoded': components['schemas']['PatchedVariantUpdateRequest']
        'multipart/form-data': components['schemas']['PatchedVariantUpdateRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerVariant']
        }
      }
    }
  }
  seller_variants_stock_update: {
    parameters: {
      query?: never
      header?: never
      path: {
        variant_id: string
      }
      cookie?: never
    }
    requestBody?: {
      content: {
        'application/json': components['schemas']['PatchedStockUpdateRequest']
        'application/x-www-form-urlencoded': components['schemas']['PatchedStockUpdateRequest']
        'multipart/form-data': components['schemas']['PatchedStockUpdateRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerVariant']
        }
      }
      /** @description STOCK_BELOW_RESERVED, details.reserved */
      409: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
    }
  }
  shops_retrieve: {
    parameters: {
      query?: never
      header?: never
      path: {
        slug: string
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
          'application/json': components['schemas']['Shop']
        }
      }
    }
  }
}
