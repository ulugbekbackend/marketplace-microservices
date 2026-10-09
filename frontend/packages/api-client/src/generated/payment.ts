// Generated from openapi/payment.json by scripts/gen-api.mjs. Do not edit.

export type paths = {
  '/api/payments/{order_id}/init/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Init Payment
     * @description Where to send the customer to pay a RESERVED order with the chosen provider.
     */
    post: operations['payments_init']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/payments/mock/{order_id}/pay': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    get?: never
    put?: never
    /**
     * Mock Pay
     * @description Development only (PAYMENT_MOCK_ENABLED): pay at once through the real
     *     ``payment.paid`` path. 404 when disabled.
     */
    post: operations['payments_mock_pay']
    delete?: never
    options?: never
    head?: never
    patch?: never
    trace?: never
  }
  '/api/payments/seller/payouts/': {
    parameters: {
      query?: never
      header?: never
      path?: never
      cookie?: never
    }
    /**
     * Seller Payouts
     * @description The seller's weekly payouts, newest week first.
     */
    get: operations['payments_seller_payouts']
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
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components['schemas']['ValidationError'][]
    }
    /** InitRequest */
    InitRequest: {
      /**
       * Provider
       * @enum {string}
       */
      provider: 'payme' | 'click'
    }
    /** InitResponse */
    InitResponse: {
      /** Redirect Url */
      redirect_url: string
    }
    /** MockPayResponse */
    MockPayResponse: {
      /** Amount Tiyin */
      amount_tiyin: number
      /**
       * Order Id
       * Format: uuid
       */
      order_id: string
      /**
       * Transaction Id
       * Format: uuid
       */
      transaction_id: string
    }
    /** PayoutOut */
    PayoutOut: {
      /** Commission Tiyin */
      commission_tiyin: number
      /**
       * Created At
       * Format: date-time
       */
      created_at: string
      /** Gross Tiyin */
      gross_tiyin: number
      /**
       * Id
       * Format: uuid
       */
      id: string
      /** Lines Count */
      lines_count: number
      /** Net Tiyin */
      net_tiyin: number
      /**
       * Period End
       * Format: date
       */
      period_end: string
      /**
       * Period Start
       * Format: date
       */
      period_start: string
      /** Status */
      status: string
    }
    /** PayoutPage */
    PayoutPage: {
      /** Items */
      items: components['schemas']['PayoutOut'][]
      /** Page */
      page: number
      /** Page Size */
      page_size: number
      /** Total */
      total: number
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
  payments_init: {
    parameters: {
      query?: never
      header?: never
      path: {
        order_id: string
      }
      cookie?: never
    }
    requestBody: {
      content: {
        'application/json': components['schemas']['InitRequest']
      }
    }
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['InitResponse']
        }
      }
      /** @description NOT_FOUND: no such order of this customer */
      404: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
      /** @description ORDER_NOT_PAYABLE / PAYMENT_IN_PROGRESS */
      409: {
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
      /** @description ORDER_SERVICE_UNAVAILABLE */
      503: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
    }
  }
  payments_mock_pay: {
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
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown
        }
        content: {
          'application/json': components['schemas']['MockPayResponse']
        }
      }
      /** @description NOT_FOUND: no such order of this customer */
      404: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
      /** @description ORDER_NOT_PAYABLE / PAYMENT_IN_PROGRESS */
      409: {
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
      /** @description ORDER_SERVICE_UNAVAILABLE */
      503: {
        headers: {
          [name: string]: unknown
        }
        content?: never
      }
    }
  }
  payments_seller_payouts: {
    parameters: {
      query?: {
        page?: number
        page_size?: number
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
          'application/json': components['schemas']['PayoutPage']
        }
      }
      /** @description PERMISSION_DENIED: not a seller */
      403: {
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
}
