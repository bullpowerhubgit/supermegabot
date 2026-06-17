export async function cancelByApi(provider, contract) {
  return {
    success: false,
    channel: 'api',
    message: `API cancellation not yet implemented for ${provider.provider}` 
  };
}
