export const SHOPIFY_API_VERSION = '2025-01';
export const API_VERSIONS = ['v1', 'v2'];
export function validateApiVersion(version: string): boolean {
  return API_VERSIONS.includes(version);
}
export function getShopifyClientConfig() {
  return { apiVersion: SHOPIFY_API_VERSION, timeout: 30000 };
}
