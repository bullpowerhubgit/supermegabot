export const providers = {
  netflix: {
    provider: 'netflix',
    channel: 'web',
    noticeDays: 0,
    supportsOnlineCancel: true,
    requiresCustomerNumber: false,
    cancelUrl: 'https://www.netflix.com/cancelplan',
    category: 'entertainment'
  },
  spotify: {
    provider: 'spotify',
    channel: 'web',
    noticeDays: 0,
    supportsOnlineCancel: true,
    requiresCustomerNumber: false,
    cancelUrl: 'https://www.spotify.com/account/cancel',
    category: 'entertainment'
  },
  adobe: {
    provider: 'adobe',
    channel: 'web',
    noticeDays: 14,
    supportsOnlineCancel: true,
    requiresCustomerNumber: false,
    cancelUrl: 'https://account.adobe.com/plans',
    category: 'software'
  },
  microsoft365: {
    provider: 'microsoft365',
    channel: 'web',
    noticeDays: 30,
    supportsOnlineCancel: true,
    requiresCustomerNumber: false,
    cancelUrl: 'https://account.microsoft.com/services',
    category: 'software'
  },
  exampleSaaS: {
    provider: 'exampleSaaS',
    channel: 'email',
    noticeDays: 30,
    supportsOnlineCancel: false,
    requiresCustomerNumber: true,
    cancelEmail: 'kuendigung@example-saas.com',
    category: 'software'
  },
  gymCompany: {
    provider: 'gymCompany',
    channel: 'manual-letter',
    noticeDays: 30,
    supportsOnlineCancel: false,
    requiresCustomerNumber: true,
    postalAddress: 'Gym Company GmbH, Vertragsservice, Berlin',
    category: 'health'
  }
};
