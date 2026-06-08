export async function cancelByWeb(provider, contract) {
  return {
    success: false,
    channel: 'web',
    message: `Open online cancellation flow manually: ${provider.cancelUrl}` 
  };
}
