// Generated from openapi/auth.json by scripts/gen-api.mjs. Do not edit.

export type paths = {
  '/api/auth/.well-known/jwks.json': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /**
     * Public signing keys (JWKS)
     * @description No gateway identity needed: the caller proves itself with a code or a token.
     */
    get: operations['.well_known_jwks.json_retrieve']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/admin/seller-applications/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** Seller applications for review */
    get: operations['admin_seller_applications_list']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/admin/seller-applications/{application_id}/approve/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /** Approve an application: the user becomes a seller */
    post: operations['admin_seller_applications_approve_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/admin/seller-applications/{application_id}/reject/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /** Reject an application */
    post: operations['admin_seller_applications_reject_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/logout/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Revoke a refresh token
     * @description No gateway identity needed: the caller proves itself with a code or a token.
     */
    post: operations['logout_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/me/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** Current user */
    get: operations['me_retrieve']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    /** Update the current user's profile */
    patch: operations['me_partial_update']
    trace?: never
  }
  '/api/auth/otp/send/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Send a sign in code by SMS
     * @description No gateway identity needed: the caller proves itself with a code or a token.
     */
    post: operations['otp_send_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/otp/verify/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Sign in with the code; creates the account on first sign in
     * @description No gateway identity needed: the caller proves itself with a code or a token.
     */
    post: operations['otp_verify_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/seller/application/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /** The caller's latest seller application */
    get: operations['seller_application_retrieve']
    put?: never
    post?: never
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/seller/apply/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /** Apply to become a seller */
    post: operations['seller_apply_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/token/refresh/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Exchange a refresh token for a new pair; the old refresh is revoked
     * @description No gateway identity needed: the caller proves itself with a code or a token.
     */
    post: operations['token_refresh_create']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/auth/verify/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /**
     * Gateway token check (ForwardAuth)
     * @description Traefik ForwardAuth target.
     *
     *     The signature and expiry are checked locally with the public key; then one primary key
     *     lookup confirms the account is still active and reads its current role, so a blocked user
     *     or a revoked role stops working at once rather than when the access token expires.
     */
    get: operations['verify_retrieve']
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
    AdminSellerApplication: {
      /** Format: date-time */
      readonly created_at: string
      readonly description: string
      /** Format: uuid */
      readonly id: string
      readonly inn: string
      /** Format: date-time */
      readonly reviewed_at: string | null
      /** Format: uuid */
      readonly reviewed_by: string | null
      readonly shop_name: string
      readonly status: components['schemas']['StatusEnum']
      readonly user: components['schemas']['Applicant']
    }
    Applicant: {
      readonly full_name: string
      /** Format: uuid */
      readonly id: string
      readonly phone: string
    }
    /** @description The shared error shape: {"error": {"code", "message", "details"}}. */
    Error: {
      error: components['schemas']['ErrorDetail']
    }
    ErrorDetail: {
      code: string
      details: {
        [key: string]: unknown
      }
      message: string
    }
    Jwk: {
      alg: string
      e: string
      kid: string
      kty: string
      n: string
      use: string
    }
    Jwks: {
      keys: components['schemas']['Jwk'][]
    }
    Login: {
      access: string
      refresh: string
      user: components['schemas']['User']
    }
    OtpSendRequest: {
      phone: string
    }
    OtpVerifyRequest: {
      code: string
      phone: string
    }
    PaginatedAdminSellerApplicationList: {
      items: components['schemas']['AdminSellerApplication'][]
      page: number
      page_size: number
      total: number
    }
    PatchedUserUpdateRequest: {
      full_name?: string
    }
    RefreshRequest: {
      refresh: string
    }
    /**
     * @description * `customer` - Customer
     *     * `seller` - Seller
     *     * `admin` - Admin
     * @enum {string}
     */
    RoleEnum: 'customer' | 'seller' | 'admin'
    SellerApplication: {
      /** Format: date-time */
      readonly created_at: string
      readonly description: string
      /** Format: uuid */
      readonly id: string
      readonly inn: string
      /** Format: date-time */
      readonly reviewed_at: string | null
      readonly shop_name: string
      readonly status: components['schemas']['StatusEnum']
    }
    SellerApplyRequest: {
      description?: string
      inn: string
      shop_name: string
    }
    /**
     * @description * `pending` - Pending
     *     * `approved` - Approved
     *     * `rejected` - Rejected
     * @enum {string}
     */
    StatusEnum: 'pending' | 'approved' | 'rejected'
    TokenPair: {
      access: string
      refresh: string
    }
    User: {
      /** Format: date-time */
      readonly date_joined: string
      readonly full_name: string
      /** Format: uuid */
      readonly id: string
      readonly phone: string
      readonly role: components['schemas']['RoleEnum']
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
  '.well_known_jwks.json_retrieve': {
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
          'application/json': components['schemas']['Jwks']
        }
      }
    }
  }
  admin_seller_applications_list: {
    parameters: {
      query?: {
        /** @description A page number within the paginated result set. */
        page?: number
        /** @description Number of results to return per page. */
        page_size?: number
        /**
         * @description * `pending` - Pending
         *     * `approved` - Approved
         *     * `rejected` - Rejected
         */
        status?: 'pending' | 'approved' | 'rejected'
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
          'application/json': components['schemas']['PaginatedAdminSellerApplicationList']
        }
      }
      /** @description Invalid input */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not authenticated */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not allowed */
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
  admin_seller_applications_approve_create: {
    parameters: {
      query?: never
      header?: never
      path: {
        application_id: string
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
          'application/json': components['schemas']['AdminSellerApplication']
        }
      }
      /** @description Not authenticated */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not allowed */
      403: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not found */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Conflict */
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
  admin_seller_applications_reject_create: {
    parameters: {
      query?: never
      header?: never
      path: {
        application_id: string
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
          'application/json': components['schemas']['AdminSellerApplication']
        }
      }
      /** @description Not authenticated */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not allowed */
      403: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not found */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Conflict */
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
  logout_create: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['RefreshRequest']
        'application/x-www-form-urlencoded': components['schemas']['RefreshRequest']
        'multipart/form-data': components['schemas']['RefreshRequest']
      }
    }
    responses: {
      /** @description No response body */
      204: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
      /** @description Invalid input */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not authenticated */
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
  me_retrieve: {
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
          'application/json': components['schemas']['User']
        }
      }
      /** @description Not authenticated */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not found */
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
  me_partial_update: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: {
      content: {
        'application/json': components['schemas']['PatchedUserUpdateRequest']
        'application/x-www-form-urlencoded': components['schemas']['PatchedUserUpdateRequest']
        'multipart/form-data': components['schemas']['PatchedUserUpdateRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['User']
        }
      }
      /** @description Invalid input */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not authenticated */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not found */
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
  otp_send_create: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['OtpSendRequest']
        'application/x-www-form-urlencoded': components['schemas']['OtpSendRequest']
        'multipart/form-data': components['schemas']['OtpSendRequest']
      }
    }
    responses: {
      /** @description No response body */
      204: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
      /** @description Invalid input */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Rate limited */
      429: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  otp_verify_create: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['OtpVerifyRequest']
        'application/x-www-form-urlencoded': components['schemas']['OtpVerifyRequest']
        'multipart/form-data': components['schemas']['OtpVerifyRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Login']
        }
      }
      /** @description Invalid input */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not allowed */
      403: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Rate limited */
      429: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
    }
  }
  seller_application_retrieve: {
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
          'application/json': components['schemas']['SellerApplication']
        }
      }
      /** @description Not authenticated */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not found */
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
  seller_apply_create: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['SellerApplyRequest']
        'application/x-www-form-urlencoded': components['schemas']['SellerApplyRequest']
        'multipart/form-data': components['schemas']['SellerApplyRequest']
      }
    }
    responses: {
      201: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['SellerApplication']
        }
      }
      /** @description Invalid input */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not authenticated */
      401: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not found */
      404: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Conflict */
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
  token_refresh_create: {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['RefreshRequest']
        'application/x-www-form-urlencoded': components['schemas']['RefreshRequest']
        'multipart/form-data': components['schemas']['RefreshRequest']
      }
    }
    responses: {
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['TokenPair']
        }
      }
      /** @description Invalid input */
      400: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['Error']
        }
      }
      /** @description Not authenticated */
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
  verify_retrieve: {
    parameters: {
      query?: {
        /** @description 1: a request without a token passes as a guest (no headers). */
        optional?: 0 | 1
      }
      header?: never
      path?: never
      cookie?: never
    }
    requestBody?: never
    responses: {
      /** @description No response body */
      200: {
        headers: {
          /** @description Seller id (the user id); sellers only. */
          'X-Seller-Id'?: string
          /** @description Verified user id. */
          'X-User-Id'?: string
          /** @description Verified role. */
          'X-User-Role'?: string
          [name: string]: unknown
        }
        content?: never
      }
      /** @description Not authenticated */
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
}
